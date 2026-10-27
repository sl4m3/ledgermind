# ADR 0003: RawRound является открытым public protocol

- **Статус:** accepted
- **Дата:** 2026-08-03

`RawRound` принадлежит отдельному открытом пакету `ledgermind-protocol`, а не Core; его контрактная версия хранится в `schema_version`.
Schema, canonical JSON, digest и conformance-набор являются общими для Integrations и Local.

Контракт содержит только структурные наблюдаемые данные завершённого раунда: сообщения, tool calls/results, границы и provenance.
Semantic fields (`hypothesis`, `confidence`, `phase`, `knowledge_id`) в него не входят.
