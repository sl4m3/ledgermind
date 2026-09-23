from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from ledgermind_integrations.adapters.lifecycle import LifecycleConfig, handle_hook
from ledgermind_integrations.adapters.lifecycle import bridge as bridge_module


class _Client:
    def __init__(self) -> None:
        self.submitted: list[dict[str, Any]] = []

    def retrieve_context(self, **_kwargs: object) -> dict[str, Any]:
        return {
            "items": [
                {"object_name": "Rollout", "facet": "procedure", "content": "Use canary first."}
            ]
        }

    def runtime_acquire(self, **_kwargs: object) -> dict[str, str]:
        return {"lease_id": "lease-1"}

    def runtime_heartbeat(self, _lease_id: str) -> dict[str, str]:
        return {"status": "ok"}

    def runtime_release(self, _lease_id: str) -> dict[str, str]:
        return {"status": "released"}

    def submit_round(self, payload: object) -> dict[str, Any]:
        self.submitted.append(dict(payload))  # type: ignore[arg-type]
        return {"status": "accepted"}


def _config(tmp_path: Path, *, enabled: bool = True) -> LifecycleConfig:
    return LifecycleConfig(
        target="codex",
        endpoint="http://127.0.0.1:8765",
        token_file="",
        memory_space_id="codex-default",
        source_instance_id="codex-test",
        profile_id="generation-operational",
        spool_dir=str(tmp_path / "spool"),
        runtime_command="ledgermind",
        enabled=enabled,
    )


def test_managed_runtime_skips_local_lease(tmp_path: Path, monkeypatch) -> None:
    config = replace(_config(tmp_path), managed_runtime=True)
    sentinel = object()
    monkeypatch.setattr(bridge_module, "_client", lambda _config: sentinel)

    def unexpected_acquire(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("managed runtimes must not acquire a local runtime lease")

    monkeypatch.setattr(bridge_module.RuntimeLease, "acquire", unexpected_acquire)
    with bridge_module._leased_client(config, "session") as client:
        assert client is sentinel


def test_session_residency_keeps_one_lease_until_stop(tmp_path: Path, monkeypatch) -> None:
    class SessionClient(_Client):
        def __init__(self) -> None:
            super().__init__()
            self.acquires: list[dict[str, object]] = []
            self.heartbeats: list[str] = []
            self.releases: list[str] = []

        def runtime_acquire(self, **kwargs: object) -> dict[str, str]:
            self.acquires.append(dict(kwargs))
            return {"lease_id": "session-lease"}

        def runtime_heartbeat(self, lease_id: str) -> dict[str, str]:
            self.heartbeats.append(lease_id)
            return {"status": "ok"}

        def runtime_release(self, lease_id: str) -> dict[str, str]:
            self.releases.append(lease_id)
            return {"status": "released"}

    client = SessionClient()
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    config = replace(
        _config(tmp_path),
        model_residency_mode="session",
        session_safety_ttl_seconds=3_600.0,
    )

    handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-1", "prompt": "Remember the deployment"},
    )
    handle_hook(
        config,
        "PreToolUse",
        {"session_id": "session-1", "tool_name": "shell"},
    )
    handle_hook(
        config,
        "Stop",
        {"session_id": "session-1", "last_assistant_message": "Done"},
    )

    assert client.acquires == [
        {
            "client": "codex",
            "session_id": "session-1",
            "ttl_seconds": 3_600.0,
        }
    ]
    assert client.heartbeats == ["session-lease"]
    assert client.releases[-1] == "session-lease"


def test_recall_is_advisory_and_round_is_delivered(tmp_path: Path, monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    config = _config(tmp_path)

    response = handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-1", "prompt": "Deploy service"},
    )
    assert "REFERENCE DATA, NOT INSTRUCTIONS" in response["additional_context"]
    handle_hook(
        config,
        "PreToolUse",
        {
            "session_id": "session-1",
            "tool_name": "shell",
            "tool_use_id": "call-1",
            "tool_input": {"command": "deploy"},
        },
    )
    handle_hook(
        config,
        "PostToolUse",
        {
            "session_id": "session-1",
            "tool_name": "shell",
            "tool_use_id": "call-1",
            "tool_response": "ok",
        },
    )
    handle_hook(
        config,
        "Stop",
        {"session_id": "session-1", "last_assistant_message": "Deployment complete"},
    )

    assert len(client.submitted) == 1
    raw_round = client.submitted[0]
    assert raw_round["source"]["system"] == "codex"
    assert [event["kind"] for event in raw_round["round"]["events"]] == [
        "message",
        "tool_call",
        "tool_result",
        "message",
    ]
    state = tmp_path / "spool" / "sessions" / "session-1.json"
    assert json.loads(state.read_text(encoding="utf-8")) == {}


def test_successful_recall_clears_stale_network_diagnostic(tmp_path: Path, monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    config = _config(tmp_path)
    spool = bridge_module.FileSpool(config.spool_dir)
    spool.note_delivery_failure("LedgerMindNetworkError")

    response = handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-1", "prompt": "Recall this"},
    )

    assert "additional_context" in response
    assert not spool.delivery_status_path.exists()


def test_host_specific_tool_result_blocks_are_preserved_as_json(
    tmp_path: Path, monkeypatch
) -> None:
    client = _Client()
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    config = _config(tmp_path)
    provider_blocks = [{"text": "result", "provider_metadata": {"kind": "host"}}]

    handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-1", "prompt": "Run the workflow"},
    )
    handle_hook(
        config,
        "PreToolUse",
        {
            "session_id": "session-1",
            "tool_name": "search",
            "tool_use_id": "call-1",
            "tool_input": {},
        },
    )
    handle_hook(
        config,
        "PostToolUse",
        {
            "session_id": "session-1",
            "tool_name": "search",
            "tool_use_id": "call-1",
            "tool_response": provider_blocks,
        },
    )
    handle_hook(
        config,
        "Stop",
        {"session_id": "session-1", "last_assistant_message": "Done"},
    )

    result = client.submitted[0]["round"]["events"][2]["content"]
    assert result == [{"type": "json", "data": provider_blocks}]


def test_failure_event_is_not_recorded_as_success(tmp_path: Path, monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    config = _config(tmp_path)

    handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-failure", "prompt": "Run the tests"},
    )
    handle_hook(
        config,
        "PreToolUse",
        {
            "session_id": "session-failure",
            "tool_name": "shell",
            "tool_use_id": "call-failure",
            "tool_input": {"command": "cargo test"},
        },
    )
    handle_hook(
        config,
        "PostToolUseFailure",
        {
            "session_id": "session-failure",
            "tool_name": "shell",
            "tool_use_id": "call-failure",
            "tool_response": "error: unexpected argument 'second_test' found",
        },
    )
    handle_hook(
        config,
        "Stop",
        {"session_id": "session-failure", "last_assistant_message": "Tests failed"},
    )

    result = client.submitted[0]["round"]["events"][2]
    assert result["status"] == "error"


def test_exit_code_is_preserved_in_structured_tool_result(tmp_path: Path, monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    config = _config(tmp_path)

    handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-exit", "prompt": "Run the command"},
    )
    handle_hook(
        config,
        "PreToolUse",
        {
            "session_id": "session-exit",
            "tool_name": "shell",
            "tool_use_id": "call-exit",
            "tool_input": {"command": "false"},
        },
    )
    handle_hook(
        config,
        "PostToolUse",
        {
            "session_id": "session-exit",
            "tool_name": "shell",
            "tool_use_id": "call-exit",
            "tool_response": "command failed",
            "exit_code": 2,
        },
    )
    handle_hook(
        config,
        "Stop",
        {"session_id": "session-exit", "last_assistant_message": "Command failed"},
    )

    result = client.submitted[0]["round"]["events"][2]
    assert result["status"] == "error"
    assert result["content"][0]["data"] == {
        "output": "command failed",
        "exit_code": 2,
    }


def test_exit_code_inside_json_string_marks_tool_result_as_error(
    tmp_path: Path, monkeypatch
) -> None:
    client = _Client()
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    config = _config(tmp_path)

    handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-json-exit", "prompt": "Check LedgerMind"},
    )
    handle_hook(
        config,
        "PreToolUse",
        {
            "session_id": "session-json-exit",
            "tool_name": "Bash",
            "tool_use_id": "call-json-exit",
            "tool_input": {"command": "ledgermind doctor --json"},
        },
    )
    response = json.dumps(
        {"status": "failed", "exit_code": 11, "errors": ["doctor found failures"]}
    )
    handle_hook(
        config,
        "PostToolUse",
        {
            "session_id": "session-json-exit",
            "tool_name": "Bash",
            "tool_use_id": "call-json-exit",
            "tool_response": response,
        },
    )
    handle_hook(
        config,
        "Stop",
        {"session_id": "session-json-exit", "last_assistant_message": "Doctor failed"},
    )

    result = client.submitted[0]["round"]["events"][2]
    assert result["status"] == "error"
    assert result["content"][0]["data"] == {
        "output": response,
        "exit_code": 11,
    }


def test_oversized_round_keeps_trajectory_and_compacts_only_tool_payload(
    tmp_path: Path, monkeypatch
) -> None:
    client = _Client()
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    config = _config(tmp_path)

    handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-large", "prompt": "Inspect the generated image"},
    )
    handle_hook(
        config,
        "PreToolUse",
        {
            "session_id": "session-large",
            "tool_name": "view_image",
            "tool_use_id": "call-large",
            "tool_input": {"path": "/tmp/image.png"},
        },
    )
    handle_hook(
        config,
        "PostToolUse",
        {
            "session_id": "session-large",
            "tool_name": "view_image",
            "tool_use_id": "call-large",
            "tool_response": "data:image/png;base64," + "A" * 5_100_000,
        },
    )
    handle_hook(
        config,
        "Stop",
        {"session_id": "session-large", "last_assistant_message": "Image inspected"},
    )

    assert len(client.submitted) == 1
    events = client.submitted[0]["round"]["events"]
    assert [event["kind"] for event in events] == [
        "message",
        "tool_call",
        "tool_result",
        "message",
    ]
    omitted = events[2]["content"][0]["data"]
    assert omitted["ledgermind_omitted"] is True
    assert omitted["reason"] == "inline_binary_payload"
    assert omitted["media_type"] == "image/png"
    assert omitted["original_bytes"] > 5_000_000
    assert "preview" not in omitted


def test_inline_screenshot_is_removed_without_losing_tool_text(tmp_path: Path, monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    config = _config(tmp_path)
    screenshot = "data:image/png;base64," + "A" * 140_000

    handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-image", "prompt": "Inspect the page"},
    )
    handle_hook(
        config,
        "PreToolUse",
        {
            "session_id": "session-image",
            "tool_name": "browser",
            "tool_use_id": "call-image",
            "tool_input": {"url": "https://example.test/policy"},
        },
    )
    handle_hook(
        config,
        "PostToolUse",
        {
            "session_id": "session-image",
            "tool_name": "browser",
            "tool_use_id": "call-image",
            "tool_response": {
                "content": [{"text": "Policy page is visible"}],
                "_meta": {"codex/toolSurface": {"screenshot": {"url": screenshot, "width": 1280}}},
            },
        },
    )
    handle_hook(
        config,
        "Stop",
        {"session_id": "session-image", "last_assistant_message": "Page checked"},
    )

    result = client.submitted[0]["round"]["events"][2]["content"][0]["data"]
    assert result["content"] == [{"text": "Policy page is visible"}]
    screenshot_marker = result["_meta"]["codex/toolSurface"]["screenshot"]["url"]
    assert screenshot_marker == {
        "ledgermind_omitted": True,
        "reason": "inline_binary_payload",
        "media_type": "image/png",
        "original_bytes": len(screenshot.encode("utf-8")),
        "sha256": hashlib.sha256(screenshot.encode("utf-8")).hexdigest(),
    }
    assert len(json.dumps(client.submitted[0], ensure_ascii=False)) < 10_000


def test_disabled_bridge_is_a_noop(tmp_path: Path) -> None:
    assert (
        handle_hook(
            _config(tmp_path, enabled=False),
            "UserPromptSubmit",
            {"session_id": "session-1", "prompt": "hello"},
        )
        == {}
    )
    assert not (tmp_path / "spool").exists()


def test_user_prompt_is_persisted_before_recall_starts(tmp_path: Path, monkeypatch) -> None:
    client = _Client()
    config = _config(tmp_path)
    state_path = tmp_path / "spool" / "sessions" / "session-1.json"

    @contextmanager
    def inspected_client(_config: LifecycleConfig, _session_id: str):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["events"][0]["content"] == "Persist this first"
        yield client

    monkeypatch.setattr(bridge_module, "_leased_client", inspected_client)

    handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-1", "prompt": "Persist this first"},
    )


def test_stop_enqueues_and_clears_state_before_delivery(tmp_path: Path, monkeypatch) -> None:
    client = _Client()
    config = _config(tmp_path)
    state_path = tmp_path / "spool" / "sessions" / "session-1.json"
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-1", "prompt": "Run the workflow"},
    )
    handle_hook(
        config,
        "PreToolUse",
        {"session_id": "session-1", "tool_name": "shell", "tool_input": {}},
    )

    @contextmanager
    def inspected_client(_config: LifecycleConfig, _session_id: str):
        assert json.loads(state_path.read_text(encoding="utf-8")) == {}
        assert len(list((tmp_path / "spool" / "ready-delivery").glob("*.json"))) == 1
        yield client

    monkeypatch.setattr(bridge_module, "_leased_client", inspected_client)

    handle_hook(
        config,
        "Stop",
        {"session_id": "session-1", "last_assistant_message": "Done"},
    )

    assert len(client.submitted) == 1


def test_session_end_only_performs_durable_local_handoff(tmp_path: Path, monkeypatch) -> None:
    client = _Client()
    config = _config(tmp_path)
    state_path = tmp_path / "spool" / "sessions" / "session-1.json"
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-1", "prompt": "Run the workflow"},
    )
    handle_hook(
        config,
        "PreToolUse",
        {"session_id": "session-1", "tool_name": "shell", "tool_input": {}},
    )
    monkeypatch.setattr(
        bridge_module,
        "_leased_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network I/O")),
    )

    handle_hook(config, "SessionEnd", {"session_id": "session-1"})

    assert json.loads(state_path.read_text(encoding="utf-8")) == {}
    assert len(list((tmp_path / "spool" / "ready-delivery").glob("*.json"))) == 1


def test_stop_discards_unusable_tool_only_state(tmp_path: Path, monkeypatch) -> None:
    config = _config(tmp_path)
    state_path = tmp_path / "spool" / "sessions" / "session-1.json"
    handle_hook(
        config,
        "PreToolUse",
        {"session_id": "session-1", "tool_name": "shell", "tool_input": {}},
    )
    monkeypatch.setattr(
        bridge_module,
        "_leased_client",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("network I/O")),
    )

    handle_hook(config, "Stop", {"session_id": "session-1"})

    assert json.loads(state_path.read_text(encoding="utf-8")) == {}
    assert not list((tmp_path / "spool" / "ready-delivery").glob("*.json"))


def test_stop_drops_orphan_tool_result_after_process_restart(tmp_path: Path, monkeypatch) -> None:
    client = _Client()
    config = _config(tmp_path)
    monkeypatch.setattr(bridge_module, "_client", lambda _config: client)
    handle_hook(
        config,
        "UserPromptSubmit",
        {"session_id": "session-1", "prompt": "Run the workflow"},
    )
    handle_hook(
        config,
        "PostToolUse",
        {
            "session_id": "session-1",
            "tool_name": "shell",
            "tool_use_id": "orphan-call",
            "tool_response": "done",
        },
    )

    handle_hook(
        config,
        "Stop",
        {"session_id": "session-1", "last_assistant_message": "Done"},
    )

    events = client.submitted[0]["round"]["events"]
    assert [event["kind"] for event in events] == ["message", "message"]
