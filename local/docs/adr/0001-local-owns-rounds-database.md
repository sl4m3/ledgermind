# ADR 0001: Local владеет rounds.db

- **Статус:** superseded
- **Superseded by:** ADR 0005: Local executes Core-owned tasks
- **Дата:** 2026-08-03

Local service владеет `rounds.db` и всеми данными локальной обработки:
RawRound metadata/payload, NormalizedRound, processing jobs, leases, inference attempts, HypothesisCandidate/records, Core command outbox, inference profiles, egress audit и локальные projection stores.

Local не открывает `knowledge.db`. Knowledge-данные доступны только через `CoreGateway` и stable IPC.

`ledgermind-integrations` не открывает ни одну из баз.
