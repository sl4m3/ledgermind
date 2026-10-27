# ADR 0003: доставка Hypothesis в Core долговечна

Статус: superseded
- **Superseded by:** ADR 0005: Local executes Core-owned tasks
- **Дата:** 2026-08-03

Старый контракт доставлял HypothesisRecord из Local. На converged boundary
Local сначала сохраняет RawRound и durable command, а Core сам строит
semantic tasks and decisions; Local исполняет только generic model/embedding
tasks и доставляет результаты через CoreGateway.

Обработка раунда не вызывает Core синхронно. Команды имеют lease, retry policy, terminal states и scoped idempotency.
Падение Local после commit не теряет Hypothesis.
