"""Durable coordinator for background round-semantic batches.

The coordinator never performs semantic interpretation.  It stores the
Core-owned task envelope, packs requests by provider limits, submits them,
persists results and hands completed tasks back to the execution worker for
normal Core delivery.

Oversized round-memory tasks are split by :class:`RoundSemanticChunkPlanner`
before packing.  Chunks live in ``batch_task_chunks``; the root task stays
``pending`` and is hidden from the normal queue until every chunk result is
available and merged.  Core still receives exactly one task result.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from ledgermind_inference.core_task_executor import GenericExecutionTask
from ledgermind_inference.providers.batch_policy import (
    BatchLimits,
    BatchPacker,
    PromptLimitExceeded,
)
from ledgermind_inference.providers.openrouter_batch import (
    BatchApiError,
    OpenRouterBatchClient,
)
from ledgermind_inference.round_semantic_chunks import (
    ChunkingError,
    RoundSemanticChunkPlanner,
)

from .batch_semantic_store import (
    BatchChunkRecord,
    BatchSemanticStore,
    BatchTaskRecord,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "anthropic/claude-haiku-5.5:batch"
DEFAULT_ENDPOINT = "/v1/chat/completions"
DEFAULT_MAX_WAIT_SECONDS = 60.0
# OpenRouter docs recommend at most one poll per minute; a webhook-notified
# deployment uses this only after a webhook fetch says "not final yet".
DEFAULT_POLL_INTERVAL_SECONDS = 60.0
# Without a webhook the poll is the primary mechanism.  With a webhook it is a
# safety net for lost deliveries and process downtime.
DEFAULT_WEBHOOK_SAFETY_SECONDS = 900.0
DEFAULT_MAX_ATTEMPTS = 5
# Packaging carries a large system prompt and contract examples; shrinking a
# retry below this floor cannot produce a feasible chunk.
DEFAULT_MIN_CHUNK_PROMPT_TOKENS = 16_000
BATCH_RETENTION_DAYS = 30
_MAX_POLL_ERRORS = 10
_MAX_CHUNK_ATTEMPTS_BEFORE_SHRINK = 4
# A just-submitted batch may be invisible to GET for a short consistency
# window.  Only a 404 older than this grace period means "expired".
_BATCH_NOT_FOUND_GRACE_SECONDS = 600.0


@dataclass(frozen=True, slots=True)
class BatchDelivery:
    """A completed batch result ready for normal Core delivery."""

    task: GenericExecutionTask
    memory_space_id: str


@dataclass(frozen=True, slots=True)
class _Outbound:
    """One request in a provider batch, backed by a root task or a chunk."""

    kind: Literal["task", "chunk"]
    record_id: str
    custom_id: str
    payload: dict[str, Any]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)  # noqa: UP017 - Python 3.10


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return _utcnow()


class BatchSemanticCoordinator:
    """Persist, pack and poll batches for one Local installation."""

    def __init__(
        self,
        *,
        store: BatchSemanticStore,
        client: OpenRouterBatchClient,
        worker_id: str,
        limits: BatchLimits | None = None,
        model: str = DEFAULT_MODEL,
        endpoint: str = DEFAULT_ENDPOINT,
        max_wait_seconds: float = DEFAULT_MAX_WAIT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        min_chunk_prompt_tokens: int = DEFAULT_MIN_CHUNK_PROMPT_TOKENS,
        chunk_planner: RoundSemanticChunkPlanner | None = None,
        callback_url: str | None = None,
        webhook_safety_interval_seconds: float = DEFAULT_WEBHOOK_SAFETY_SECONDS,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if max_wait_seconds < 0:
            raise ValueError("max_wait_seconds must not be negative")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if webhook_safety_interval_seconds <= 0:
            raise ValueError("webhook_safety_interval_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if min_chunk_prompt_tokens < 1_000:
            raise ValueError("min_chunk_prompt_tokens must be at least 1000")
        self._store = store
        self._client = client
        self._worker_id = worker_id
        self._limits = limits if limits is not None else BatchLimits.openrouter()
        self._model = model
        self._endpoint = endpoint
        self._max_wait_seconds = float(max_wait_seconds)
        self._poll_interval_seconds = float(poll_interval_seconds)
        self._max_attempts = int(max_attempts)
        self._callback_url = callback_url.strip() if callback_url else None
        if self._callback_url is not None and not self._callback_url.startswith(
            "https://"
        ):
            logger.warning(
                "batch callback URL is not public HTTPS; OpenRouter rejects it",
                extra={"callback_scheme": self._callback_url.split(":", 1)[0]},
            )
        self._webhook_safety_interval_seconds = float(webhook_safety_interval_seconds)
        self._min_chunk_prompt_tokens = min(
            int(min_chunk_prompt_tokens),
            self._limits.target_prompt_tokens_per_request,
        )
        self._planner = (
            chunk_planner
            if chunk_planner is not None
            else RoundSemanticChunkPlanner(
                max_prompt_tokens=self._limits.target_prompt_tokens_per_request
            )
        )
        self._last_tick = 0.0

    # ------------------------------------------------------------ task intake

    @staticmethod
    def is_batch_task(task: GenericExecutionTask) -> bool:
        operation_input = task.operation_input or {}
        if (
            isinstance(operation_input, dict)
            and operation_input.get("round_memory") is not None
        ):
            return True
        if not isinstance(task.operation, str):
            return False
        # Object Resolution is a bounded semantic call (at most 32 ephemeral
        # objects).  It needs no size chunking, but it still belongs to the
        # batch-only semantic core.
        if task.operation == "object_resolution":
            return True
        return task.operation.startswith(("operational_round_memory_", "round_memory_"))

    def has_result(self, task: GenericExecutionTask) -> bool:
        record = self._store.get(task.task_id)
        return record is not None and record.status in {"result_ready", "completed"}

    def enqueue(self, task: GenericExecutionTask, memory_space_id: str) -> bool:
        contract = task.model_request.output_contract if task.model_request else None
        digest = contract.get("schema_digest") if isinstance(contract, dict) else None
        return self._store.enqueue(
            task_id=task.task_id,
            memory_space_id=memory_space_id,
            custom_id=_custom_id(task.task_id),
            payload=task.model_dump(mode="json"),
            contract_digest=str(digest) if isinstance(digest, str) and digest else None,
        )

    def mark_delivered(self, task_id: str) -> None:
        self._store.mark_delivered(task_id)

    # ------------------------------------------------------------------ ticks

    def tick(self) -> list[BatchDelivery]:
        """Advance polling, merging and submission; return deliverable tasks."""
        started = time.monotonic()
        try:
            self._poll_in_flight()
        except Exception as exc:  # noqa: BLE001 - one tick must not kill the worker
            logger.warning(
                "batch polling tick failed",
                extra={"error_type": type(exc).__name__},
            )
        try:
            self._merge_ready_roots()
        except Exception as exc:  # noqa: BLE001 - one tick must not kill the worker
            logger.warning(
                "batch merge tick failed",
                extra={"error_type": type(exc).__name__},
            )
        try:
            self._submit_pending()
        except Exception as exc:  # noqa: BLE001 - one tick must not kill the worker
            logger.warning(
                "batch submission tick failed",
                extra={"error_type": type(exc).__name__},
            )

        deliveries: list[BatchDelivery] = []
        for record in self._store.result_ready():
            try:
                task = GenericExecutionTask.model_validate(record.payload)
            except Exception as exc:  # noqa: BLE001 - durable payload corruption
                logger.warning(
                    "stored batch task payload is invalid",
                    extra={"task_id": record.task_id, "error_type": type(exc).__name__},
                )
                self._store.mark_failed(record.task_id, "invalid_batch_payload")
                continue
            deliveries.append(
                BatchDelivery(task=task, memory_space_id=record.memory_space_id)
            )
        self._last_tick = started
        return deliveries

    # --------------------------------------------------------------- polling

    def _poll_in_flight(self) -> None:
        for job in self._store.jobs():
            if _utcnow() < _parse_timestamp(job.next_poll_at):
                continue
            try:
                snapshot = self._client.get_batch(job.batch_id)
            except BatchApiError as exc:
                self._handle_poll_error(job, exc)
                continue

            status = str(snapshot.get("status") or "unknown")
            if status == "completed":
                self._consume_completed(job.batch_id, snapshot)
                self._store.delete_job(job.batch_id)
                continue
            if status in {"failed", "cancelled", "expired"}:
                self._abandon_batch(job.batch_id, f"batch_{status}")
                continue
            self._store.update_job(
                job.batch_id,
                status=status,
                next_poll_at=self._next_poll_at(),
                poll_errors=0,
            )

    def _handle_poll_error(self, job: Any, exc: BatchApiError) -> None:
        if exc.expired:
            age = (_utcnow() - _parse_timestamp(job.submitted_at)).total_seconds()
            if exc.status_code == 404 and age < _BATCH_NOT_FOUND_GRACE_SECONDS:
                self._store.update_job(
                    job.batch_id,
                    status=job.status,
                    next_poll_at=self._future(
                        min(60.0, self._poll_interval_seconds * 2)
                    ),
                    poll_errors=job.poll_errors,
                )
                return
            self._abandon_batch(job.batch_id, "batch_expired")
            return
        if not exc.retryable:
            self._fail_batch(job.batch_id, "batch_poll_rejected")
            return
        errors = job.poll_errors + 1
        if errors >= _MAX_POLL_ERRORS:
            self._abandon_batch(job.batch_id, "batch_poll_failed")
            return
        delay = min(300.0, self._poll_interval_seconds * (2 ** min(errors, 5)))
        self._store.update_job(
            job.batch_id,
            status=job.status,
            next_poll_at=self._future(delay),
            poll_errors=errors,
        )

    def _consume_completed(self, batch_id: str, snapshot: dict[str, Any]) -> None:
        parsed = self._client.parse_batch_results(snapshot)
        for record in self._store.tasks_for_batch(batch_id):
            self._consume_task_entry(record, parsed.get(record.custom_id))
        for chunk in self._store.chunks_for_batch(batch_id):
            self._consume_chunk_entry(chunk, parsed.get(chunk.custom_id))

    def _consume_task_entry(
        self, record: BatchTaskRecord, entry: dict[str, Any] | None
    ) -> None:
        if entry is None:
            self._store.mark_failed(record.task_id, "batch_result_missing")
            return
        if entry.get("status") == "completed" and entry.get("output") is not None:
            self._store.mark_result(
                record.task_id,
                output=entry["output"],
                usage=entry.get("usage"),
            )
            return

        error_code = str(entry.get("error_code") or "batch_request_failed")
        if _is_transient_entry(entry) and record.attempts < self._max_attempts:
            self._store.requeue_task(record.task_id, error_code)
        else:
            self._store.mark_failed(record.task_id, error_code)

    def _consume_chunk_entry(
        self, chunk: BatchChunkRecord, entry: dict[str, Any] | None
    ) -> None:
        if entry is None:
            self._store.mark_chunk_failed(chunk.chunk_id, "batch_result_missing")
            return
        if entry.get("status") == "completed" and entry.get("output") is not None:
            self._store.mark_chunk_result(
                chunk.chunk_id,
                output=entry["output"],
                usage=entry.get("usage"),
            )
            return

        error_code = str(entry.get("error_code") or "batch_request_failed")
        if _is_transient_entry(entry) and chunk.attempts < self._max_attempts:
            self._store.requeue_chunk(chunk.chunk_id, error_code)
        else:
            self._store.mark_chunk_failed(chunk.chunk_id, error_code)

    def _abandon_batch(self, batch_id: str, error_code: str) -> None:
        requeued = self._store.requeue_batch(batch_id, error_code)
        for task_id in requeued:
            record = self._store.get(task_id)
            if record is not None and record.attempts >= self._max_attempts:
                self._store.mark_failed(task_id, "retry_exhausted")
        chunk_ids = self._store.requeue_chunks_batch(batch_id, error_code)
        for chunk_id in chunk_ids:
            chunk = self._store.get_chunk(chunk_id)
            if chunk is not None and chunk.attempts >= self._max_attempts:
                self._store.mark_chunk_failed(chunk_id, "retry_exhausted")
        self._store.delete_job(batch_id)

    def _fail_batch(self, batch_id: str, error_code: str) -> None:
        for record in self._store.tasks_for_batch(batch_id):
            if record.status == "submitted":
                self._store.mark_failed(record.task_id, error_code)
        for chunk in self._store.chunks_for_batch(batch_id):
            if chunk.status == "submitted":
                self._store.mark_chunk_failed(chunk.chunk_id, error_code)
        self._store.delete_job(batch_id)

    # ------------------------------------------------------------------ merge

    def _merge_ready_roots(self) -> None:
        for root_task_id in self._store.chunked_root_ids():
            root = self._store.get(root_task_id)
            chunks = self._store.chunks_for_root(root_task_id)
            if root is None or not chunks:
                continue
            if any(chunk.status == "failed" for chunk in chunks):
                self._reset_chunked_root(root_task_id, "chunk_failed")
                continue
            if not all(
                chunk.status in {"result_ready", "completed"} for chunk in chunks
            ):
                continue
            outputs = [
                chunk.result for chunk in chunks if isinstance(chunk.result, dict)
            ]
            if len(outputs) != len(chunks):
                self._reset_chunked_root(root_task_id, "chunk_result_missing")
                continue
            try:
                task = GenericExecutionTask.model_validate(root.payload)
                merged = self._planner.merge(task, outputs)
            except Exception as exc:  # noqa: BLE001 - invalid merge is durable
                logger.warning(
                    "chunk merge failed",
                    extra={
                        "root_task_id": root_task_id,
                        "error_type": type(exc).__name__,
                    },
                )
                self._reset_chunked_root(root_task_id, "chunk_merge_failed")
                continue
            self._store.complete_chunked_root(
                root_task_id,
                output=merged,
                usage=_sum_usage(chunks),
            )

    def _reset_chunked_root(self, root_task_id: str, error_code: str) -> None:
        attempts = self._store.reset_chunked_root(root_task_id, error_code)
        if attempts >= self._max_attempts:
            self._store.mark_failed(root_task_id, "chunk_retry_exhausted")

    # ------------------------------------------------------------ submission

    def _submit_pending(self) -> None:
        if len(self._store.jobs()) >= self._limits.max_in_flight_batches:
            return
        pending_tasks = self._store.pending(limit=2_000)
        pending_chunks = self._store.pending_chunks(limit=2_000)
        if not pending_tasks and not pending_chunks:
            return

        now = _utcnow()
        created = [record.created_at for record in pending_tasks]
        created.extend(chunk.created_at for chunk in pending_chunks)
        oldest = min(created, key=_parse_timestamp)
        ready_by_age = (
            now - _parse_timestamp(oldest)
        ).total_seconds() >= self._max_wait_seconds
        ready_by_count = (
            len(pending_tasks) + len(pending_chunks)
            >= self._limits.max_requests_per_batch
        )
        if not ready_by_age and not ready_by_count:
            return

        packer = BatchPacker(self._limits)
        outbound_by_custom_id: dict[str, _Outbound] = {}
        batches: list[list[dict[str, Any]]] = []

        def add(payload: dict[str, Any], outbound: _Outbound) -> None:
            outbound_by_custom_id[outbound.custom_id] = outbound
            batches.extend(packer.add(payload))

        for record in pending_tasks:
            try:
                task = GenericExecutionTask.model_validate(record.payload)
            except Exception as exc:  # noqa: BLE001 - durable payload corruption
                logger.warning(
                    "stored batch task payload is invalid",
                    extra={"task_id": record.task_id, "error_type": type(exc).__name__},
                )
                self._store.mark_failed(record.task_id, "invalid_batch_payload")
                continue
            budget = self._chunk_budget(record)
            try:
                if self._planner.needs_chunking(task, max_prompt_tokens=budget):
                    self._plan_root_or_fail(record, task, budget)
                    continue
            except ChunkingError as exc:
                logger.warning(
                    "batch task cannot be chunked",
                    extra={"task_id": record.task_id, "error_type": type(exc).__name__},
                )
                self._store.mark_failed(record.task_id, "chunk_plan_failed")
                continue
            try:
                payload = self._format_request(record)
            except PromptLimitExceeded:
                self._plan_root_or_fail(record, task, budget)
                continue
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "batch task cannot be packed",
                    extra={"task_id": record.task_id, "error_type": type(exc).__name__},
                )
                self._store.mark_failed(record.task_id, "input_too_large")
                continue
            add(
                payload,
                _Outbound("task", record.task_id, record.custom_id, payload),
            )

        # Planning above may have produced new chunks, so read them again.
        for chunk in self._store.pending_chunks(limit=2_000):
            try:
                payload = self._format_chunk_request(chunk)
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "batch chunk cannot be packed",
                    extra={
                        "chunk_id": chunk.chunk_id,
                        "error_type": type(exc).__name__,
                    },
                )
                self._store.mark_chunk_failed(chunk.chunk_id, "input_too_large")
                continue
            add(
                payload,
                _Outbound("chunk", chunk.chunk_id, chunk.custom_id, payload),
            )

        if (
            ready_by_age
            or ready_by_count
            or packer.pending_requests >= self._limits.max_requests_per_batch
            or packer.pending_bytes >= self._limits.max_batch_bytes
            or packer.pending_prompt_tokens >= self._limits.soft_total_prompt_tokens
        ):
            final = packer.flush()
            if final is not None:
                batches.append(final)

        for batch in batches:
            if len(self._store.jobs()) >= self._limits.max_in_flight_batches:
                break
            self._submit_batch(batch, outbound_by_custom_id)

    def _chunk_budget(self, record: BatchTaskRecord) -> int:
        attempts = max(0, min(record.attempts, _MAX_CHUNK_ATTEMPTS_BEFORE_SHRINK))
        budget = self._limits.target_prompt_tokens_per_request // (2**attempts)
        return min(
            self._planner.max_prompt_tokens,
            max(self._min_chunk_prompt_tokens, budget),
        )

    def _plan_root_or_fail(
        self,
        record: BatchTaskRecord,
        task: GenericExecutionTask,
        budget: int,
    ) -> None:
        try:
            planned = self._plan_root(record, task, budget)
        except ChunkingError as exc:
            logger.warning(
                "batch task cannot be chunked",
                extra={"task_id": record.task_id, "error_type": type(exc).__name__},
            )
            planned = False
        if not planned:
            self._store.mark_failed(record.task_id, "chunk_plan_failed")

    def _plan_root(
        self,
        record: BatchTaskRecord,
        task: GenericExecutionTask,
        budget: int,
    ) -> bool:
        plan = self._planner.plan(task, max_prompt_tokens=budget)
        if plan is None:
            return False
        chunks = [
            {
                "chunk_id": chunk.task_id,
                "custom_id": _custom_id(chunk.task_id),
                "payload": chunk.model_dump(mode="json"),
            }
            for chunk in plan.chunks
        ]
        return self._store.plan_chunks(record.task_id, chunks)

    def _format_request(self, record: BatchTaskRecord) -> dict[str, Any]:
        task = GenericExecutionTask.model_validate(record.payload)
        return self._format_task_request(task, record.custom_id)

    def _format_chunk_request(self, chunk: BatchChunkRecord) -> dict[str, Any]:
        task = GenericExecutionTask.model_validate(chunk.payload)
        return self._format_task_request(task, chunk.custom_id)

    def _format_task_request(
        self,
        task: GenericExecutionTask,
        custom_id: str,
    ) -> dict[str, Any]:
        spec = task.model_request
        if spec is None:
            raise ValueError("batch task has no model request")
        contract = dict(spec.output_contract or {})
        schema = contract.get("json_schema")
        schema_name = contract.get("contract_name")
        return self._client.format_request(
            custom_id,
            messages=[message.model_dump(mode="json") for message in spec.messages],
            max_tokens=spec.max_output_tokens,
            schema=schema if isinstance(schema, dict) else None,
            schema_name=str(schema_name) if schema_name is not None else None,
            reasoning_effort="low",
        )

    def _submit_batch(
        self,
        batch: list[dict[str, Any]],
        outbound_by_custom_id: dict[str, _Outbound],
    ) -> None:
        outbound = [
            outbound_by_custom_id[payload["custom_id"]]
            for payload in batch
            if payload.get("custom_id") in outbound_by_custom_id
        ]
        if not outbound:
            return
        task_ids = [item.record_id for item in outbound if item.kind == "task"]
        chunk_ids = [item.record_id for item in outbound if item.kind == "chunk"]
        try:
            batch_id = self._client.submit_batch(
                batch,
                model=self._model,
                endpoint=self._endpoint,
                callback_url=self._callback_url,
            )
        except BatchApiError as exc:
            if exc.status_code == 413 and len(batch) > 1:
                middle = len(batch) // 2
                self._submit_batch(batch[:middle], outbound_by_custom_id)
                self._submit_batch(batch[middle:], outbound_by_custom_id)
                return
            if exc.retryable:
                logger.warning(
                    "transient batch submission failure; keeping tasks pending",
                    extra={"status_code": exc.status_code},
                )
                return
            for task_id in task_ids:
                self._store.mark_failed(
                    task_id,
                    f"batch_submit_{exc.status_code or 'error'}",
                )
            for chunk_id in chunk_ids:
                self._store.mark_chunk_failed(
                    chunk_id,
                    f"batch_submit_{exc.status_code or 'error'}",
                )
            return

        self._store.record_batch_submission(
            task_ids,
            chunk_ids,
            batch_id,
            expires_at=self._expiry(),
            next_poll_at=self._initial_poll_at(),
        )

    # ----------------------------------------------------------------- helpers

    def _initial_poll_at(self) -> str:
        """Webhook mode waits for the event; polling mode starts immediately."""
        if self._callback_url is not None:
            return self._future(self._webhook_safety_interval_seconds)
        # Polling mode checks once right after submission; later checks use the
        # documented one-per-minute cadence.
        return self._future(0)

    def _next_poll_at(self) -> str:
        return self._future(self._poll_interval_seconds)

    def _future(self, seconds: float) -> str:
        return (_utcnow() + timedelta(seconds=seconds)).isoformat()

    def _expiry(self) -> str:
        return (_utcnow() + timedelta(days=BATCH_RETENTION_DAYS)).isoformat()


def _is_transient_entry(entry: dict[str, Any]) -> bool:
    error_code = str(entry.get("error_code") or "")
    status_code = entry.get("status_code")
    return error_code in {"json_parse_error", "empty_choices"} or (
        isinstance(status_code, int)
        and (status_code == 429 or 500 <= status_code <= 599)
    )


def _sum_usage(chunks: list[BatchChunkRecord]) -> dict[str, Any]:
    """Sum chunk usage; provider token counts stay integers, cost stays exact."""
    totals: dict[str, Any] = {}
    decimals: dict[str, Decimal] = {}
    for chunk in chunks:
        for key, value in (chunk.usage or {}).items():
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, int):
                totals[key] = int(totals.get(key, 0)) + value
                continue
            if isinstance(value, float):
                totals[key] = float(totals.get(key, 0.0)) + value
                continue
            if isinstance(value, str):
                try:
                    decimals[key] = decimals.get(key, Decimal(0)) + Decimal(value)
                except InvalidOperation:
                    totals.setdefault(key, value)
                continue
            totals.setdefault(key, value)
    for key, value in decimals.items():
        totals[key] = str(value)
    return totals


def _custom_id(task_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", task_id or "")
    if not safe:
        safe = "task"
    if len(safe) > 64:
        safe = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
    return safe
