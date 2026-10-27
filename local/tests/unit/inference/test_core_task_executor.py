from __future__ import annotations

import sqlite3
import threading
import time

from ledgermind_local.embedding_purpose import EmbeddingPurpose
from ledgermind_local.inference.cancellation import CancellationToken
from ledgermind_local.inference.core_task_executor import (
    CoreTaskExecutor,
    EmbeddingRequestSpec,
    GenericExecutionTask,
    ModelRequestSpec,
    _error_category,
)
from ledgermind_local.inference.embedding_provider import EmbeddingProvider
from ledgermind_local.inference.profile_slots import (
    ProfileSlot,
    StoreBackedProfileResolver,
)
from ledgermind_local.inference.profile_store import InferenceProfileStore
from ledgermind_local.inference.profiles import InferenceProfile
from ledgermind_local.inference.providers.base import (
    ChatMessage,
    ModelResponse,
)
from ledgermind_local.inference.secrets import SecretStore
from ledgermind_local.inference.structured_json_provider import (
    StructuredJsonProvider,
)
from ledgermind_local.persistence import rounds_migrations as migrations
from ledgermind_local.scheduler.core_execution_task_worker import _core_result_payload

SECRET_VALUE = "TOP_SECRET"


class _FakeCompleter:
    provider_kind = "openai_compatible"

    def __init__(
        self, content: str, *, error: Exception | None = None, delay: float = 0.0
    ) -> None:
        self.content = content
        self.error = error
        self.delay = delay
        self.requests: list[object] = []

    def complete_json(self, request, token=None, cancellation_token=None):
        self.requests.append(request)
        if token is not None:
            token.raise_if_cancelled()
        if self.error is not None:
            raise self.error
        if self.delay:
            deadline = time.monotonic() + self.delay
            while time.monotonic() < deadline:
                if token is not None:
                    token.raise_if_cancelled()
                time.sleep(0.01)
        return ModelResponse(
            content=self.content,
            model=request.model,
            attempts=1,
            request_bytes=len(request.encoded_payload()),
            response_bytes=len(self.content.encode()),
            status_code=200,
        )

    def close(self) -> None:
        return None


class _FakeVectorizer:
    def __init__(
        self,
        *,
        dimension: int,
        fingerprint: str = "sha256:test",
        vectors: list[list[float]] | None = None,
        delay: float = 0.0,
    ) -> None:
        self._dimension = dimension
        self._fingerprint = fingerprint
        self._vectors = vectors
        self._delay = delay

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode(self, texts):
        if self._delay:
            time.sleep(self._delay)
        if self._vectors is not None:
            return self._vectors
        return [[float(len(text))] * self._dimension for text in texts]

    def close(self) -> None:
        return None


def _memory_store() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    migrations.apply_migrations(connection)
    connection.execute(
        "INSERT INTO memory_spaces(memory_space_id, source_client, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("space", "tests", "2026-08-03T00:00:00Z", "2026-08-03T00:00:00Z"),
    )
    store = InferenceProfileStore(connection)
    store.upsert(
        InferenceProfile(
            profile_id="operational-default",
            base_url="https://provider.example/v1",
            model="op-model",
            secret_ref="provider-main",
        )
    )
    store.upsert(
        InferenceProfile(
            profile_id="background-default",
            base_url="https://provider.example/v1",
            model="bg-model",
            secret_ref="bg-main",
        )
    )
    store.upsert(
        InferenceProfile(
            profile_id="object-resolution-default",
            base_url="https://provider.example/v1",
            model="object-resolution-model",
            secret_ref="object-resolution-main",
        )
    )
    store.upsert(
        InferenceProfile(
            profile_id="embedding-default",
            base_url="https://provider.example/v1",
            model="embed-model",
            secret_ref="embed-main",
        )
    )
    store.bind_slot("space", slot="operational", profile_id="operational-default")
    store.bind_slot("space", slot="background", profile_id="background-default")
    store.bind_slot(
        "space", slot="object_resolution", profile_id="object-resolution-default"
    )
    store.bind_slot(
        "space",
        slot="embedding",
        profile_id="embedding-default",
    )
    connection.commit()
    return connection


def _resolver() -> StoreBackedProfileResolver:
    return StoreBackedProfileResolver(
        InferenceProfileStore(_memory_store()),
    )


def _secrets(tmp_path) -> SecretStore:
    secrets = SecretStore(tmp_path / "secrets.json")
    secrets.put("provider-main", SECRET_VALUE)
    secrets.put("object-resolution-main", SECRET_VALUE)
    secrets.put("embed-main", SECRET_VALUE)
    return secrets


def _json_provider(fake: _FakeCompleter, tmp_path) -> StructuredJsonProvider:
    return StructuredJsonProvider(
        profile_resolver=_resolver(),
        secret_store=_secrets(tmp_path),
        provider_factory=lambda profile, secret: fake,
    )


def _embedding_provider(vectorizer: _FakeVectorizer) -> EmbeddingProvider:
    return EmbeddingProvider(vectorizer_factory=lambda: vectorizer)


def _executor(
    tmp_path,
    *,
    json_provider: StructuredJsonProvider | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    json_timeout: float = 5.0,
    embed_timeout: float = 5.0,
) -> CoreTaskExecutor:
    if json_provider is None:
        json_provider = _json_provider(_FakeCompleter('{"ok": true}'), tmp_path)
    if embedding_provider is None:
        embedding_provider = _embedding_provider(
            _FakeVectorizer(dimension=4, fingerprint="m1")
        )
    return CoreTaskExecutor(
        json_provider=json_provider,
        embedding_provider=embedding_provider,
        profile_resolver=_resolver(),
        generate_json_timeout_seconds=json_timeout,
        embed_texts_timeout_seconds=embed_timeout,
    )


def _json_task(
    *, operation: str | None = "extract_values", completer: _FakeCompleter
) -> GenericExecutionTask:
    return GenericExecutionTask(
        task_id="task-1",
        task_kind="generate_json",
        operation=operation,
        profile_slot=ProfileSlot.OPERATIONAL,
        model_request=ModelRequestSpec(
            messages=(
                ChatMessage(role="system", content="Return JSON only."),
                ChatMessage(role="user", content="Extract values."),
            ),
            max_output_tokens=100,
            response_format={"type": "json_object"},
        ),
        lease={"memory_space_id": "space"},
    )


def _embed_task(
    *,
    texts: tuple[str, ...] = ("hello world", "second text"),
    purpose: EmbeddingPurpose = "knowledge",
    subject_refs: tuple[str, ...] | None = None,
    dimensions: int | None = 3,
    task_id: str = "task-2",
) -> GenericExecutionTask:
    return GenericExecutionTask(
        task_id=task_id,
        task_kind="embed_texts",
        operation="consolidate_values",
        profile_slot=ProfileSlot.EMBEDDING,
        embedding_request=EmbeddingRequestSpec(
            texts=texts,
            purpose=purpose,
            subject_refs=subject_refs,
            dimensions=dimensions,
        ),
        lease={"memory_space_id": "space"},
    )


def test_generic_json_task_completes_with_output_and_payload_free_audit(
    tmp_path,
) -> None:
    fake = _FakeCompleter('{"answer": 42}')
    executor = _executor(tmp_path, json_provider=_json_provider(fake, tmp_path))

    result = executor.execute(_json_task(completer=fake))

    assert result.status == "completed"
    assert result.output == {"answer": 42}
    assert result.error_code is None
    audit = result.egress_audit
    assert audit.task_id == "task-1"
    assert audit.task_kind == "generate_json"
    assert audit.profile_id == "operational-default"
    assert audit.provider == "openai_compatible"
    assert audit.model == "op-model"
    assert audit.input_bytes > 0
    assert audit.output_bytes > 0
    assert audit.status == "completed"
    dumped = audit.model_dump_json()
    assert SECRET_VALUE not in dumped
    assert "Extract values." not in dumped


def test_empty_recheck_attempt_forces_configured_provider_fallback(
    tmp_path, monkeypatch
) -> None:
    fake = _FakeCompleter('{"claims": [], "objects": []}')
    provider = _json_provider(fake, tmp_path)
    original_generate = provider.generate_json
    fallback_flags: list[bool] = []

    def capture_fallback(**kwargs):
        fallback_flags.append(bool(kwargs.get("force_provider_fallback")))
        return original_generate(**kwargs)

    monkeypatch.setattr(provider, "generate_json", capture_fallback)
    executor = _executor(tmp_path, json_provider=provider)
    task = _json_task(completer=fake).model_copy(
        update={
            "operation": "execution_semantic",
            "structured_generation": {
                "root_task_id": "task-1",
                "parent_task_id": "task-1",
                "attempt_number": 1,
                "attempt_kind": "empty_recheck",
                "contract_digest": "sha256:test",
            },
        }
    )

    result = executor.execute(task)

    assert result.status == "completed"
    assert fallback_flags == [True]


def test_object_resolution_task_uses_dedicated_profile_slot_and_model(tmp_path) -> None:
    fake = _FakeCompleter('{"groups": []}')
    executor = _executor(tmp_path, json_provider=_json_provider(fake, tmp_path))
    task = _json_task(completer=fake).model_copy(
        update={
            "task_id": "object-resolution-task",
            "task_kind": "object_resolution",
            "operation": "object_resolution",
            "profile_slot": ProfileSlot.OBJECT_RESOLUTION,
        }
    )

    result = executor.execute(task)

    assert result.status == "completed"
    assert result.egress_audit.profile_id == "object-resolution-default"
    assert result.egress_audit.model == "object-resolution-model"


def test_embedding_task_completes_with_vectors_and_audit(tmp_path) -> None:
    embedding_provider = _embedding_provider(
        _FakeVectorizer(dimension=3, fingerprint="m1")
    )
    executor = _executor(tmp_path, embedding_provider=embedding_provider)

    result = executor.execute(_embed_task())

    assert result.status == "completed"
    assert result.output is None
    assert result.embedding_result is not None
    assert len(result.embedding_result.vectors) == 2
    assert result.embedding_result.dimensions == 3
    assert result.embedding_result.model == "embed-model"
    assert result.embedding_result.model_version.startswith("sha256:")
    assert len(result.embedding_result.model_version) == len("sha256:") + 64
    audit = result.egress_audit
    assert audit.task_kind == "embed_texts"
    assert audit.profile_id == "embedding-default"
    assert audit.provider == "local"
    assert audit.status == "completed"
    assert SECRET_VALUE not in audit.model_dump_json()
    assert "hello world" not in audit.model_dump_json()


def test_embedding_result_wire_projection_excludes_local_renderer_metadata(tmp_path) -> None:
    result = _executor(tmp_path).execute(_embed_task(dimensions=4))

    payload = _core_result_payload(result)
    assert set(payload["embedding_result"]) == {
        "vectors",
        "model",
        "model_version",
        "dimensions",
        "purpose",
    }


def test_subject_query_embedding_task_is_accepted_without_domain_interpretation(
    tmp_path,
) -> None:
    executor = _executor(tmp_path)

    result = executor.execute(
        _embed_task(
            texts=("language LocaleProvider",),
            purpose="subject_query",
            subject_refs=("subject:language",),
            dimensions=4,
            task_id="subject-query-task",
        )
    )

    assert result.status == "completed"
    assert result.embedding_result is not None
    assert result.embedding_result.purpose == "subject_query"


def test_unknown_task_kind_is_reported_without_crashing(tmp_path) -> None:
    task = GenericExecutionTask(
        task_id="task-3",
        task_kind="run_code",
        profile_slot=ProfileSlot.OPERATIONAL,
        lease={"memory_space_id": "space"},
    )

    result = _executor(tmp_path).execute(task)

    assert result.status == "unknown_task_kind"
    assert result.error_code == "unknown_task_kind"
    assert result.egress_audit.status == "unknown_task_kind"


def test_operation_does_not_affect_local_dispatch(tmp_path) -> None:
    fake = _FakeCompleter('{"v": 1}')
    executor = _executor(tmp_path, json_provider=_json_provider(fake, tmp_path))

    result_a = executor.execute(
        _json_task(operation="extract_values", completer=fake)
    )
    result_b = executor.execute(
        _json_task(operation="consolidate_values", completer=fake)
    )

    assert result_a.status == "completed"
    assert result_b.status == "completed"
    assert result_a.output == result_b.output
    assert result_a.egress_audit.task_kind == result_b.egress_audit.task_kind
    assert [request.model_dump() for request in fake.requests] == [
        request.model_dump() for request in fake.requests
    ]


def test_operation_none_is_treated_like_any_other_value(tmp_path) -> None:
    fake = _FakeCompleter('{"v": 1}')
    executor = _executor(tmp_path, json_provider=_json_provider(fake, tmp_path))

    result = executor.execute(_json_task(operation=None, completer=fake))

    assert result.status == "completed"
    assert result.output == {"v": 1}


def test_invalid_json_response_fails_with_structured_code(tmp_path) -> None:
    fake = _FakeCompleter("not json at all")
    executor = _executor(tmp_path, json_provider=_json_provider(fake, tmp_path))

    result = executor.execute(_json_task(completer=fake))

    assert result.status == "failed"
    assert result.error_code == "invalid_json_response"
    assert result.egress_audit.status == "failed"
    assert SECRET_VALUE not in result.egress_audit.model_dump_json()


def test_error_taxonomy_keeps_transport_json_shape_semantic_language_and_grounding_distinct() -> None:
    expected = {
        "provider_timeout": "transport_failure",
        "invalid_json_response": "json_parse_failure",
        "schema_shape_failure": "schema_shape_failure",
        "semantic_validation_failure": "semantic_validation_failure",
        "language_fidelity_failure": "language_fidelity_failure",
        "grounding_failure": "grounding_failure",
    }

    assert {code: _error_category(code) for code in expected} == expected


def test_json_array_response_is_rejected(tmp_path) -> None:
    fake = _FakeCompleter("[1, 2, 3]")
    executor = _executor(tmp_path, json_provider=_json_provider(fake, tmp_path))

    result = executor.execute(_json_task(completer=fake))

    assert result.status == "failed"
    assert result.error_code == "invalid_json_response"


def test_embedding_nan_vector_fails_with_structured_code(tmp_path) -> None:
    embedding_provider = _embedding_provider(
        _FakeVectorizer(
            dimension=2, fingerprint="m1", vectors=[[1.0, float("nan")]]
        )
    )
    executor = _executor(tmp_path, embedding_provider=embedding_provider)

    result = executor.execute(
        _embed_task(texts=("bad text",), dimensions=2, task_id="task-nan")
    )

    assert result.status == "failed"
    assert result.error_code == "embedding_non_finite"


def test_embedding_expected_dimension_mismatch_fails(tmp_path) -> None:
    embedding_provider = _embedding_provider(
        _FakeVectorizer(dimension=3, fingerprint="m1")
    )
    executor = _executor(tmp_path, embedding_provider=embedding_provider)

    result = executor.execute(
        _embed_task(texts=("text",), dimensions=8, task_id="task-dim")
    )

    assert result.status == "failed"
    assert result.error_code == "embedding_dimension_mismatch"
    assert result.egress_audit.profile_id == "embedding-default"


def test_missing_profile_slot_fails_with_profile_missing(tmp_path) -> None:
    fake = _FakeCompleter('{"ok": true}')
    executor = _executor(tmp_path, json_provider=_json_provider(fake, tmp_path))
    task = _json_task(completer=fake).model_copy(
        update={"lease": {"memory_space_id": "unknown-space"}}
    )

    result = executor.execute(task)

    assert result.status == "failed"
    assert result.error_code == "profile_missing"
    assert result.egress_audit.profile_id is None
    assert not fake.requests


def test_pre_cancelled_token_fails_with_cancelled_status(tmp_path) -> None:
    fake = _FakeCompleter('{"answer": 42}')
    executor = _executor(tmp_path, json_provider=_json_provider(fake, tmp_path))
    token = CancellationToken()
    token.cancel()

    result = executor.execute(_json_task(completer=fake), cancellation_token=token)

    assert result.status == "cancelled"
    assert result.error_code == "cancelled"
    assert result.egress_audit.status == "cancelled"


def test_mid_flight_cancellation_interrupts_generate_json(tmp_path) -> None:
    token = CancellationToken()
    fake = _FakeCompleter('{"answer": 42}', delay=0.5)
    executor = _executor(tmp_path, json_provider=_json_provider(fake, tmp_path))

    def cancel_soon() -> None:
        time.sleep(0.05)
        token.cancel()

    thread = threading.Thread(target=cancel_soon)
    thread.start()
    result = executor.execute(_json_task(completer=fake), cancellation_token=token)
    thread.join(timeout=1)

    assert result.status == "cancelled"
    assert result.error_code == "cancelled"
    assert not thread.is_alive()


def test_generate_json_timeout_is_applied_separately(tmp_path) -> None:
    token = CancellationToken()
    fake = _FakeCompleter('{"answer": 42}', delay=0.5)
    executor = _executor(
        tmp_path, json_provider=_json_provider(fake, tmp_path), json_timeout=0.05
    )

    result = executor.execute(_json_task(completer=fake), cancellation_token=token)

    assert result.status == "timeout"
    assert result.error_code == "timeout"
    assert token.cancelled


def test_embedding_timeout_is_applied_separately(tmp_path) -> None:
    embedding_provider = _embedding_provider(
        _FakeVectorizer(dimension=3, fingerprint="m1", delay=0.5)
    )
    executor = _executor(
        tmp_path, embedding_provider=embedding_provider, embed_timeout=0.05
    )

    result = executor.execute(
        _embed_task(texts=("slow",), task_id="task-slow-embed")
    )

    assert result.status == "timeout"
    assert result.error_code == "timeout"
    assert result.egress_audit.status == "timeout"
