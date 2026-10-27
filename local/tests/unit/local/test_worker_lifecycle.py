from __future__ import annotations

import threading

from ledgermind_local.scheduler.guarded_loop import GuardedWorkerLoop
from ledgermind_local.scheduler.worker_state import WorkerState


def test_shutdown_timeout_reports_live_thread_and_late_exit_clears_running_state() -> None:
    entered = threading.Event()
    release = threading.Event()

    class Worker:
        def process_once(self):
            entered.set()
            release.wait(timeout=2)

    loop = GuardedWorkerLoop(
        Worker(),
        name="blocked-worker",
        poll_interval_seconds=0,
        initial_backoff_seconds=0,
        max_backoff_seconds=0,
    )
    thread = loop.start()
    assert entered.wait(timeout=1)
    assert loop.is_alive() is True

    shutdown = loop.shutdown(timeout=0.01)

    assert shutdown.stopped is False
    assert shutdown.timed_out is True
    assert shutdown.thread_name == thread.name
    assert shutdown.current_item_id is None
    assert loop.is_alive() is True
    timed_out = loop.state.snapshot()
    assert timed_out.stopping is True
    assert timed_out.shutdown_timed_out is True
    assert timed_out.running is True

    release.set()
    assert loop.join(timeout=1) is True
    assert loop.is_alive() is False
    stopped = loop.state.snapshot()
    assert stopped.running is False
    assert stopped.stopping is False
    assert stopped.current_item_id is None
    repeated = loop.shutdown(timeout=0)
    assert repeated.stopped is True
    assert loop.state.snapshot().stopping is False


def test_result_observer_can_mark_worker_degraded_for_handled_stats() -> None:
    observed: list[tuple[object | None, WorkerState]] = []
    loop: GuardedWorkerLoop

    class Result:
        failed = 1

    class Worker:
        def process_once(self):
            return Result()

    def observe(result: object | None, state: WorkerState) -> None:
        observed.append((result, state))
        state.mark_degraded()
        loop.request_stop()

    loop = GuardedWorkerLoop(
        Worker(),
        name="observed-worker",
        poll_interval_seconds=0,
        result_observer=observe,
    )
    loop.start()

    assert loop.join(timeout=1) is True
    assert len(observed) == 1
    assert isinstance(observed[0][0], Result)
    snapshot = loop.state.snapshot()
    assert snapshot.degraded is True
    assert snapshot.last_progress_at is not None
    assert snapshot.processed_count == 1


def test_worker_state_records_safe_failure_progress_and_degraded_status() -> None:
    state = WorkerState("state-worker")

    state.mark_started(item_id="sensitive-item")
    state.mark_error("RuntimeError", item_id="sensitive-item")
    state.mark_progress()
    state.mark_degraded()
    state.mark_stopping()
    state.mark_shutdown_timed_out()

    snapshot = state.snapshot()
    assert snapshot.last_error_code == "RuntimeError"
    assert snapshot.last_iteration_failure_count == 1
    assert snapshot.last_progress_at is not None
    assert snapshot.degraded is True
    assert snapshot.stopping is True
    assert snapshot.shutdown_timed_out is True
    assert "sensitive exception text" not in str(state.as_dict())


def test_guarded_loop_state_never_stores_exception_text() -> None:
    failed = threading.Event()

    class Worker:
        def process_once(self):
            failed.set()
            raise RuntimeError("secret provider payload")

    loop = GuardedWorkerLoop(
        Worker(),
        name="safe-error-worker",
        initial_backoff_seconds=10,
        max_backoff_seconds=10,
    )
    loop.start()
    assert failed.wait(timeout=1)

    shutdown = loop.shutdown(timeout=1)

    assert shutdown.stopped is True
    state = loop.state.as_dict()
    assert state["last_error_code"] == "RuntimeError"
    assert "secret provider payload" not in str(state)


def test_result_observer_failure_does_not_kill_worker_loop() -> None:
    calls = 0
    observed = threading.Event()
    loop: GuardedWorkerLoop

    class Worker:
        def process_once(self):
            nonlocal calls
            calls += 1
            if calls == 1:
                return "first"
            loop.request_stop()
            return "second"

    def observe(result: object | None, state: WorkerState) -> None:
        observed.set()
        raise RuntimeError("observer payload must not escape")

    loop = GuardedWorkerLoop(
        Worker(),
        name="observer-failure-worker",
        poll_interval_seconds=0,
        result_observer=observe,
    )
    loop.start()

    assert observed.wait(timeout=1)
    assert loop.join(timeout=1) is True
    assert calls == 2
    assert loop.state.snapshot().processed_count == 2


def test_degraded_result_is_published_before_observer_health_observation() -> None:
    observation_published = threading.Event()
    release_observer = threading.Event()
    loop: GuardedWorkerLoop

    class Result:
        degraded = True

    class Worker:
        def process_once(self):
            return Result()

    observation: dict[str, object] = {}

    def observe(result: object | None, state: WorkerState) -> None:
        assert isinstance(result, Result)
        observation["degraded"] = True
        observation_published.set()
        assert release_observer.wait(timeout=1)
        state.mark_degraded()
        loop.request_stop()

    loop = GuardedWorkerLoop(
        Worker(),
        name="atomic-publication-worker",
        poll_interval_seconds=0,
        result_observer=observe,
    )
    loop.start()
    try:
        assert observation_published.wait(timeout=1)
        snapshot = loop.state.snapshot()
        health_view = {
            "healthy": snapshot.healthy,
            "degraded": observation["degraded"],
        }
        assert health_view == {"healthy": False, "degraded": True}
        outcome = loop.last_outcome
        assert outcome is not None
        assert outcome.snapshot == snapshot
    finally:
        loop.request_stop()
        release_observer.set()
        assert loop.join(timeout=1) is True
