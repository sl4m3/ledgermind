from __future__ import annotations

import json
import stat
import time
from pathlib import Path
from typing import Any, cast

import pytest

from ledgermind_integrations.adapters.hermes.config import HermesConfig
from ledgermind_integrations.adapters.hermes.hooks import HermesRoundCapture, PendingCaptureWorker
from ledgermind_integrations.adapters.hermes.runtime import HermesPluginRuntime
from ledgermind_integrations.runtime.spool import FileSpool, SpoolFullError


def _config(tmp_path: Path) -> HermesConfig:
    return HermesConfig(
        endpoint="http://127.0.0.1:8765",
        token_file=str(tmp_path / "token"),
        memory_space_id="workspace_01",
        source_instance_id="src_hermes_local",
        profile_id="default",
        state_db_path=str(tmp_path / "state.db"),
        spool_dir=str(tmp_path / "spool"),
        context_timeout_seconds=0.1,
        max_pending_attempts=2,
    )


def _pending(tmp_path: Path) -> tuple[HermesRoundCapture, FileSpool]:
    spool = FileSpool(tmp_path / "spool")
    capture = HermesRoundCapture(_config(tmp_path), spool)
    capture.capture_or_defer(
        session_id="session-1",
        round_id="round-1",
        started_at="2026-08-02T20:00:00Z",
        completed_at="2026-08-02T20:01:00Z",
        events=[],
    )
    return capture, spool


def test_spool_is_private_and_claims_ready_atomically(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", inflight_ttl_seconds=0.1)
    ready = spool.enqueue_ready("round-1", {"id": "round-1"})
    assert stat.S_IMODE(spool.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(spool.ready_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(ready.stat().st_mode) == 0o600

    claimed = spool.pop_ready()
    assert [name for name, _ in claimed] == ["round-1.json"]
    assert not ready.exists()
    assert (spool.inflight_dir / "round-1.json").exists()
    assert claimed[0][1]["delivery"]["worker_id"]
    assert claimed[0][1]["delivery"]["claimed_at"]


def test_spool_reclaims_expired_inflight(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", inflight_ttl_seconds=0.1)
    spool.enqueue_ready("round-1", {"id": "round-1"})
    spool.pop_ready()
    inflight = spool.inflight_dir / "round-1.json"
    old = time.time() - 10
    payload = json.loads(inflight.read_text(encoding="utf-8"))
    payload["delivery"]["claimed_at"] = old
    inflight.write_text(json.dumps(payload), encoding="utf-8")

    spool._reclaim_expired_inflight()
    assert not inflight.exists()
    assert (spool.ready_dir / "round-1.json").exists()
    assert [name for name, _ in spool.pop_ready()] == ["round-1.json"]


def test_spool_rejects_queue_over_limits(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", max_files=1)
    spool.enqueue_ready("round-1", {"id": "round-1"})
    with pytest.raises(SpoolFullError):
        spool.enqueue_ready("round-2", {"id": "round-2"})


def test_spool_rejects_raw_round_over_shared_payload_limit(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", max_payload_bytes=10)

    with pytest.raises(SpoolFullError, match="payload byte limit exceeded"):
        spool.enqueue_ready("round-1", {"payload": "too-large"})


def test_spool_keys_cannot_escape_queue_directory(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")

    path = spool.enqueue_pending("../../escape", {"id": "round-1"})

    assert path.parent == spool.pending_dir
    assert path.resolve().is_relative_to(spool.pending_dir.resolve())
    assert not (tmp_path / "escape.json").exists()


def test_spool_moves_do_not_count_source_twice(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", max_files=1, inflight_ttl_seconds=0.1)
    spool.enqueue_ready("round-1", {"id": "round-1"})
    item_name, payload = spool.pop_ready()[0]
    spool.retry(item_name, payload)
    assert (spool.ready_dir / item_name).exists()


def test_spool_backoff_move_does_not_count_inflight_source_twice(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool", max_files=1)
    spool.enqueue_ready("round-1", {"id": "round-1"})
    item_name, payload = spool.pop_ready()[0]
    payload["delivery"]["next_attempt_at"] = time.time() + 60
    spool.retry(item_name, payload)

    assert spool.pop_ready() == []
    assert (spool.ready_dir / item_name).exists()


def test_pending_capture_retry_waits_for_final_event(tmp_path: Path) -> None:
    capture, spool = _pending(tmp_path)
    worker = PendingCaptureWorker(capture, max_attempts=2)

    assert worker.run_once(lambda _: None) == 0
    assert spool.pop_pending() == []
    pending_path = next(spool.pending_dir.glob("*.json"))
    pending_payload = json.loads(pending_path.read_text(encoding="utf-8"))
    assert pending_payload["delivery"]["attempts"] == 1
    assert pending_payload["delivery"]["next_attempt_at"] > time.time()
    assert worker.run_once(lambda _: None) == 0
    assert spool.stats().pending_capture == 1
    assert spool.stats().failed == 0


def test_pending_pop_honors_due_time_and_sorts_by_schedule(tmp_path: Path) -> None:
    spool = FileSpool(tmp_path / "spool")
    first = spool.enqueue_pending("first", {"session_id": "s1"})
    second = spool.enqueue_pending("second", {"session_id": "s2"})
    first_payload = json.loads(first.read_text(encoding="utf-8"))
    second_payload = json.loads(second.read_text(encoding="utf-8"))
    first_payload["delivery"]["next_attempt_at"] = time.time() + 20
    second_payload["delivery"]["next_attempt_at"] = time.time() + 10
    spool.retry_pending(first.name, first_payload)
    spool.retry_pending(second.name, second_payload)

    assert spool.pop_pending() == []
    now = time.time()
    first_payload["delivery"]["next_attempt_at"] = now - 2
    second_payload["delivery"]["next_attempt_at"] = now - 1
    spool.retry_pending(first.name, first_payload)
    spool.retry_pending(second.name, second_payload)

    assert [name for name, _ in spool.pop_pending()] == ["first.json", "second.json"]


def test_pending_promotion_survives_ready_queue_full(tmp_path: Path) -> None:
    capture, spool = _pending(tmp_path)

    def reject_enqueue(*_args: Any, **_kwargs: Any) -> Path:
        raise SpoolFullError("test queue full")

    spool.enqueue_ready = reject_enqueue  # type: ignore[method-assign]
    worker = PendingCaptureWorker(capture, max_attempts=2)
    final_events = [
        {
            "event_id": "round-1:user",
            "kind": "message",
            "role": "user",
            "content": "hello",
        },
        {
            "event_id": "round-1:assistant",
            "kind": "message",
            "role": "assistant",
            "content": "world",
            "final": True,
        },
    ]

    assert worker.run_once(lambda _: final_events) == 0
    assert spool.stats().pending_capture == 1


def test_pending_promotion_reuses_its_queue_slot(tmp_path: Path) -> None:
    capture, spool = _pending(tmp_path)
    spool.max_files = 1
    worker = PendingCaptureWorker(capture, max_attempts=2)
    final_events = [
        {
            "event_id": "round-1:user",
            "kind": "message",
            "role": "user",
            "content": "hello",
        },
        {
            "event_id": "round-1:assistant",
            "kind": "message",
            "role": "assistant",
            "content": "world",
            "final": True,
        },
    ]

    assert worker.run_once(lambda _: final_events) == 1
    assert spool.stats().pending_capture == 0
    assert spool.stats().ready_delivery == 1


def test_post_llm_does_not_raise_when_capture_and_pending_spool_are_full(
    tmp_path: Path,
) -> None:
    spool = FileSpool(tmp_path / "spool", max_files=1)
    spool.enqueue_ready("occupied", {"id": "occupied"})
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(Any, object()),
        spool=spool,
    )
    try:
        runtime.on_post_llm_call(
            session_id="session-1",
            turn_id="turn-1",
            user_message="hello",
            assistant_response="world",
        )
    finally:
        runtime.stop()


def test_pre_llm_context_timeout_is_bounded(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(
            Any,
            type(
                "SlowClient",
                (),
                {"retrieve_context": lambda *_args, **_kwargs: time.sleep(1.0)},
            )(),
        ),
        spool=FileSpool(tmp_path / "spool"),
    )
    started = time.monotonic()
    try:
        assert runtime.on_pre_llm_call(user_message="slow") is None
    finally:
        runtime.stop()
    assert time.monotonic() - started < 0.5


def test_pre_llm_malformed_context_fails_open(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(
            Any,
            type("MalformedClient", (), {"retrieve_context": lambda *_args, **_kwargs: None})(),
        ),
        spool=FileSpool(tmp_path / "spool"),
    )
    try:
        assert runtime.on_pre_llm_call(user_message="hello") is None
    finally:
        runtime.stop()


def test_post_llm_wakes_delivery_loop(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(Any, object()),
        spool=FileSpool(tmp_path / "spool"),
    )
    woken: list[bool] = []
    runtime.loop.wake = lambda: woken.append(True)  # type: ignore[attr-defined]
    try:
        runtime.on_post_llm_call(
            session_id="session-1",
            turn_id="turn-1",
            user_message="hello",
            assistant_response="world",
        )
    finally:
        runtime.stop()
    assert woken == [True]


def test_hooks_without_turn_id_share_one_active_round(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(
            Any,
            type("ContextClient", (), {"retrieve_context": lambda *_args, **_kwargs: None})(),
        ),
        spool=FileSpool(tmp_path / "spool"),
    )
    try:
        runtime.on_pre_llm_call(session_id="session-1", user_message="hello")
        active = runtime.get_active_round("session-1")
        assert active is not None
        round_id = active.round_id

        runtime.on_pre_tool_call(
            session_id="session-1",
            tool_name="read_file",
            args={"path": "README.md"},
        )
        runtime.on_post_tool_call(
            session_id="session-1",
            result={"ok": True},
            status="success",
        )
        runtime.on_post_llm_call(
            session_id="session-1",
            user_message="hello",
            assistant_response="world",
        )

        payload = json.loads(next((runtime.spool.ready_dir).glob("*.json")).read_text())[
            "request"
        ]
        assert payload["source"]["round_id"] == round_id
        assert [event["kind"] for event in payload["round"]["events"]] == [
            "message",
            "tool_call",
            "tool_result",
            "message",
        ]
    finally:
        runtime.shutdown()


def test_new_pre_llm_defers_previous_round_with_exact_boundaries(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(
            Any,
            type("ContextClient", (), {"retrieve_context": lambda *_args, **_kwargs: None})(),
        ),
        spool=FileSpool(tmp_path / "spool"),
    )
    try:
        runtime.on_pre_llm_call(
            session_id="session-1",
            user_message="first",
            first_message_id=10,
            user_message_id=10,
        )
        previous = runtime.get_active_round("session-1")
        assert previous is not None
        runtime.on_pre_tool_call(
            session_id="session-1",
            tool_call_id="call-1",
            tool_name="read_file",
            args={"path": "README.md"},
            message_id=11,
        )
        runtime.on_pre_llm_call(
            session_id="session-1",
            user_message="second",
            first_message_id=20,
            user_message_id=20,
        )

        pending_path = runtime.spool.pending_dir / f"{previous.round_id}.json"
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        assert pending["session_id"] == "session-1"
        assert pending["round_id"] == previous.round_id
        assert pending["external_turn_id"] is None
        assert pending["first_message_id"] == 10
        assert pending["last_message_id"] == 11
        assert pending["user_message_id"] == 10
        assert pending["assistant_message_id"] is None
        assert pending["known_event_ids"]
        assert pending["known_tool_events"]
        assert runtime.get_active_round("session-1") is not None
        assert runtime.get_active_round("session-1").round_id != previous.round_id  # type: ignore[union-attr]
    finally:
        runtime.shutdown()


def test_session_end_does_not_stop_other_sessions(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(
            Any,
            type("ContextClient", (), {"retrieve_context": lambda *_args, **_kwargs: None})(),
        ),
        spool=FileSpool(tmp_path / "spool"),
    )
    runtime.start()
    try:
        runtime.on_pre_llm_call(session_id="session-1", user_message="first")
        runtime.on_session_end(session_id="session-1")

        assert runtime.runtime_started is True
        assert runtime.runtime_stopped is False
        assert "session-1" not in runtime.active_rounds
        assert runtime.session_states.get("session-1") is None

        runtime.on_pre_llm_call(session_id="session-2", user_message="second")
        assert runtime.get_active_round("session-2") is not None
    finally:
        runtime.shutdown()


def test_three_sequential_sessions_share_one_runtime_process(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(
            Any,
            type("ContextClient", (), {"retrieve_context": lambda *_args, **_kwargs: None})(),
        ),
        spool=FileSpool(tmp_path / "spool"),
    )
    runtime.start()
    try:
        for index in range(3):
            session_id = f"session-{index}"
            runtime.on_pre_llm_call(session_id=session_id, user_message=f"hello-{index}")
            if index == 2:
                runtime.on_session_finalize(session_id=session_id)
            else:
                runtime.on_session_end(session_id=session_id)
            assert runtime.runtime_started is True
            assert runtime.runtime_stopped is False

        assert len(list(runtime.spool.pending_dir.glob("*.json"))) == 3
    finally:
        runtime.shutdown()


def test_executor_closes_only_during_shutdown(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(Any, object()),
        spool=FileSpool(tmp_path / "spool"),
    )
    executor = runtime._context_executor
    try:
        runtime.finish_session("session-1")
        assert executor._shutdown is False
        runtime.stop()
        assert executor._shutdown is False
        runtime.start()
        assert runtime.runtime_started is True
    finally:
        runtime.shutdown()
    assert executor._shutdown is True


def test_runtime_can_restart_after_worker_stop(tmp_path: Path) -> None:
    runtime = HermesPluginRuntime(
        config=_config(tmp_path),
        client=cast(Any, object()),
        spool=FileSpool(tmp_path / "spool"),
    )
    runtime.start()
    first_thread = runtime.loop.thread
    try:
        runtime.stop()
        assert first_thread is not None
        assert not first_thread.is_alive()
        runtime.start()
        assert runtime.runtime_started is True
        assert runtime.loop.thread is not first_thread
        assert runtime.loop.thread is not None
        assert runtime.loop.thread.is_alive()
    finally:
        runtime.shutdown()
