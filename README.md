# ledgermind-core

Чистый ядро-корпус LedgerMind 4.0: домен, приложения и порты без привязки к локальной инфраструктуре.

Ядро содержит:
- доменные объекты и правила (`domain/`);
- сценарии приложений (`application/`);
- внешние порты для адаптеров (`ports/`);
- контрактные модели (`contracts/`).

## Быстрый пример (через поддельный UoW)

```python
from datetime import datetime, timezone

from application import (
    IngestAtomHandler,
    IngestAtomResult,
    JsonIngestAtomResultSerializer,
    IngestAtomCommand,
    calculate_idempotency_key,
    calculate_request_hash,
)
from application.digests import calculate_source_round_key
from application.get_knowledge import GetKnowledgeHandler, GetKnowledgeQuery
from application.ingest_atom import IdempotencyConflict
from domain import AtomContent, ExtractionInfo, SourceReference
from domain.policies import IsolatedPatternPolicy
from tests.fakes import FakeClock, FakeIdentifierFactory, FakeUnitOfWork


def _source_round(now: datetime) -> SourceReference:
    return SourceReference(
        source_system="hermes",
        source_instance_id="instance-1",
        source_profile_id="default",
        source_session_id="session-1",
        source_round_id="round-1",
        first_message_id="m-1",
        final_message_id="m-2",
        message_ids=("m-1", "m-2"),
        source_digest="sha256:" + "a" * 64,
        source_schema_version=1,
        resolver_version=1,
    )


def _content() -> AtomContent:
    return AtomContent(
        title="Новая идея",
        target="architecture",
        statement="Знания должны жить в ядре и быть версионными",
        rationale="Стабильная модель для локальной службы",
        result="",
        artifacts=(),
    )


def _extraction() -> ExtractionInfo:
    return ExtractionInfo(
        host="hermes",
        provider="openrouter",
        model="gpt",
        prompt_version=1,
        schema_version=1,
        purpose="ledgermind.atom.extract",
    )


if __name__ == "__main__":
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    clock = FakeClock(now)

    # Фейковый UoW для демонстрации API без БД
    uow = FakeUnitOfWork(clock=clock)

    handler = IngestAtomHandler(
        uow_factory=lambda: uow,
        policy=IsolatedPatternPolicy(),
        clock=clock,
        identifiers=FakeIdentifierFactory(),
        serializer=JsonIngestAtomResultSerializer(),
    )

    source = _source_round(now)
    source_round_key = calculate_source_round_key(source)
    idempotency_key = calculate_idempotency_key(
        source_round_key=source_round_key,
        extraction_prompt_version=1,
        extraction_schema_version=1,
    )

    command = IngestAtomCommand(
        idempotency_key=idempotency_key,
        request_hash=calculate_request_hash({"round": source_round_key}),
        memory_space_id="hermes:instance-1:default",
        source=source,
        content=_content(),
        extraction=_extraction(),
    )

    result = handler.handle(command)
    assert isinstance(result, IngestAtomResult)

    read = GetKnowledgeHandler(lambda: uow).handle(
        GetKnowledgeQuery(
            memory_space_id="hermes:instance-1:default",
            knowledge_id=result.knowledge_id,
        )
    )

    print(f"knowledge created: {read.knowledge_id} v{read.version}")

    # Демонстрация идемпотентности: повторный вызов вернёт тот же ответ
    result2 = handler.handle(command)
    print(f"duplicate={result2.duplicate}")

    # Проверка конфликта idempotency_key при другом request_hash
    bad_command = IngestAtomCommand(
        idempotency_key=idempotency_key,
        request_hash="sha256:" + "b" * 64,
        memory_space_id="hermes:instance-1:default",
        source=source,
        content=_content(),
        extraction=_extraction(),
    )
    try:
        handler.handle(bad_command)
    except IdempotencyConflict:
        print("idempotency conflict: expected")
```

## Структура

```text
src/
  application/
  contracts/
  domain/
  ports/

docs/
  adr/
  invariants.md
  application-contracts.md
```

## Проверка ядра

После выполнения этапа 2.13 рекомендуется выполнить:

```bash
python -m pytest tests/unit
python -m ruff check .
python -m mypy src tests
python -m build
python -m twine check dist/*
```

В окружении текущего контейнера доступны Python 3.14 и `venv`.
Для проверки многоверсионной установки необходимо запускать отдельные окружения для Python 3.10/3.11/3.12.
