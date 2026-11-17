from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

from ledgermind_local.inference.core_task_executor import GenericExecutionTask
from ledgermind_local.scheduler import core_execution_task_worker as worker_module
from ledgermind_local.scheduler.core_execution_task_worker import (
    CoreExecutionTaskWorker,
)


def _task(
    task_id: str,
    *,
    task_kind: str = "decide",
    parallel_safe: bool | None = None,
) -> GenericExecutionTask:
    operation_input = None
    if parallel_safe is not None:
        operation_input = {"parallel_safe": parallel_safe}
    return GenericExecutionTask(
        task_id=task_id,
        task_kind=task_kind,
        profile_slot="operational",
        operation_input=operation_input,
    )


class _Connection:
    def __init__(self, spaces: list[str]) -> None:
        self._spaces = spaces

    def commit(self) -> None:
        pass

    def execute(self, _query: str):
        return SimpleNamespace(fetchall=lambda: [(space,) for space in self._spaces])

    def close(self) -> None:
        pass


class _Gateway:
    def __init__(
        self,
        spaces: list[str],
        poll_tasks: list[dict[str, object]],
    ) -> None:
        self._spaces = spaces
        self._poll_tasks = poll_tasks
        self.poll_limits: list[int] = []

    def require_capabilities(self, _capability: str) -> None:
        pass

    def poll_execution_tasks(self, command):
        self.poll_limits.append(command.limit)
        return SimpleNamespace(tasks=list(self._poll_tasks))

    def submit_execution_result(self, _command):
        return SimpleNamespace(accepted=True)

    def fail_execution_task(self, _command):
        return None


def _worker(
    monkeypatch,
    *,
    executor,
    tasks: list[GenericExecutionTask],
    spaces: list[str] | None = None,
    **kwargs,
) -> tuple[CoreExecutionTaskWorker, _Gateway, list[tuple[str, float]]]:
    spaces = spaces or ["space-1"]
    by_id = {task.task_id: task for task in tasks}
    monkeypatch.setattr(
        worker_module,
        "execution_task_from_wire",
        lambda raw, _space: by_id[str(raw["task_id"])],
    )
    monkeypatch.setattr(
        worker_module.migrations, "apply_migrations", lambda _connection: None
    )
    gateway = _Gateway(spaces, [{"task_id": task.task_id} for task in tasks])
    worker = CoreExecutionTaskWorker(
        database_path="unused.db",
        gateway=gateway,
        executor=executor,
        worker_id="async-worker",
        connection_factory=lambda _path: _Connection(spaces),
        **kwargs,
    )
    delivered: list[tuple[str, float]] = []
    monkeypatch.setattr(
        worker,
        "_deliver_result",
        lambda task, _result, _space: delivered.append(
            (task.task_id, time.monotonic())
        ),
    )
    return worker, gateway, delivered


def _completed(task_id: str):
    return SimpleNamespace(
        task_id=task_id,
        task_kind="decide",
        status="completed",
        error_code=None,
        egress_audit=None,
    )


def test_three_decisions_run_concurrently_with_generation_concurrency_one(
    monkeypatch,
) -> None:
    all_started = None
    started = 0

    class Executor:
        async def execute_async(self, task, cancellation_token=None):
            nonlocal started
            started += 1
            if started == 3:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=5)
            return _completed(task.task_id)

    tasks = [_task(f"decision-{index}") for index in range(3)]
    worker, _gateway, delivered = _worker(
        monkeypatch,
        executor=Executor(),
        tasks=tasks,
        generation_concurrency=1,
    )

    def run():
        nonlocal all_started
        all_started = asyncio.Event()
        assert worker.process_once() == 3
        worker.wait_for_idle(timeout=10)

    loop_thread = threading.Thread(target=run)
    loop_thread.start()
    loop_thread.join(timeout=15)

    assert not loop_thread.is_alive()
    assert started == 3
    assert [task_id for task_id, _ in delivered] == [
        "decision-0",
        "decision-1",
        "decision-2",
    ]
    worker.close()


def test_generation_lane_is_capped(monkeypatch) -> None:
    lock = threading.Lock()
    active = 0
    maximum = 0

    class Executor:
        def execute(self, task, cancellation_token=None):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.05)
            with lock:
                active -= 1
            return _completed(task.task_id)

    tasks = [
        _task(f"generation-{index}", task_kind="generate_json", parallel_safe=True)
        for index in range(4)
    ]
    worker, _gateway, delivered = _worker(
        monkeypatch,
        executor=Executor(),
        tasks=tasks,
        generation_concurrency=2,
    )

    assert worker.process_once() == 4
    worker.wait_for_idle(timeout=10)

    assert maximum == 2
    assert [task_id for task_id, _ in delivered] == [
        "generation-0",
        "generation-1",
        "generation-2",
        "generation-3",
    ]
    worker.close()


def test_serial_lane_preserves_space_order(monkeypatch) -> None:
    started: list[str] = []
    lock = threading.Lock()

    class Executor:
        def execute(self, task, cancellation_token=None):
            with lock:
                started.append(task.task_id)
            delays = {
                "serial-0": 0.06,
                "serial-1": 0.01,
                "serial-2": 0.05,
                "serial-3": 0.01,
            }
            time.sleep(delays[task.task_id])
            return _completed(task.task_id)

    tasks = [
        _task(f"serial-{index}", task_kind="generate_json", parallel_safe=False)
        for index in range(4)
    ]
    worker, _gateway, delivered = _worker(
        monkeypatch, executor=Executor(), tasks=tasks, generation_concurrency=4
    )

    assert worker.process_once() == 4
    worker.wait_for_idle(timeout=10)

    assert started == ["serial-0", "serial-1", "serial-2", "serial-3"]
    assert [task_id for task_id, _ in delivered] == [
        "serial-0",
        "serial-1",
        "serial-2",
        "serial-3",
    ]
    worker.close()


def test_dispatch_returns_without_waiting_for_the_batch(monkeypatch) -> None:
    started = threading.Event()
    release = threading.Event()

    class Executor:
        async def execute_async(self, task, cancellation_token=None):
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            return _completed(task.task_id)

    worker, _gateway, delivered = _worker(
        monkeypatch,
        executor=Executor(),
        tasks=[_task("slow-decision")],
        lease_seconds=30,
    )

    began = time.monotonic()
    assert worker.process_once() == 1
    elapsed = time.monotonic() - began

    assert elapsed < 1.0
    assert started.wait(timeout=5)
    assert delivered == []
    try:
        worker.wait_for_idle(timeout=0.05)
    except TimeoutError:
        pass
    else:
        raise AssertionError("worker must still have an in-flight decision")

    release.set()
    worker.wait_for_idle(timeout=10)
    assert [task_id for task_id, _ in delivered] == ["slow-decision"]
    worker.close()


def test_close_waits_for_inflight_work(monkeypatch) -> None:
    started = threading.Event()

    class Executor:
        def execute(self, task, cancellation_token=None):
            started.set()
            time.sleep(0.2)
            return _completed(task.task_id)

    worker, _gateway, delivered = _worker(
        monkeypatch,
        executor=Executor(),
        tasks=[_task("slow-generation", task_kind="generate_json", parallel_safe=True)],
    )

    assert worker.process_once() == 1
    assert started.wait(timeout=5)
    assert delivered == []

    worker.close()

    assert [task_id for task_id, _ in delivered] == ["slow-generation"]


def test_decisions_execute_while_a_generation_task_is_still_running(
    monkeypatch,
) -> None:
    generation_started = threading.Event()
    release_generation = threading.Event()
    decisions_finished = threading.Event()
    finished = 0

    class Executor:
        async def execute_async(self, task, cancellation_token=None):
            nonlocal finished
            finished += 1
            if finished == 3:
                decisions_finished.set()
            return _completed(task.task_id)

        def execute(self, task, cancellation_token=None):
            generation_started.set()
            release_generation.wait(timeout=5)
            return _completed(task.task_id)

    tasks = [
        _task("slow-generation", task_kind="generate_json", parallel_safe=True),
        _task("decision-0"),
        _task("decision-1"),
        _task("decision-2"),
    ]
    worker, _gateway, delivered = _worker(
        monkeypatch,
        executor=Executor(),
        tasks=tasks,
        generation_concurrency=1,
    )

    assert worker.process_once() == 4
    assert generation_started.wait(timeout=5)
    # All decision provider calls finish while the generation call is still
    # blocked; delivery is ordered per space and therefore waits.
    assert decisions_finished.wait(timeout=5)
    assert worker.lane_inflight()["generation"] == 1
    assert delivered == []
    release_generation.set()
    worker.wait_for_idle(timeout=10)

    assert [task_id for task_id, _ in delivered] == [
        "slow-generation",
        "decision-0",
        "decision-1",
        "decision-2",
    ]
    worker.close()
