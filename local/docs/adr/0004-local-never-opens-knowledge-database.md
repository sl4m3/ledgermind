# ADR 0004: Local никогда не открывает knowledge.db

- **Статус:** accepted
- **Дата:** 2026-08-03

Local не содержит Python Core backend и не имеет transitional production fallback.
Единственный runtime путь к knowledge database проходит через supervised
`CoreGateway` к отдельному signed Rust process `ledgermind-core`; Local никогда
не импортирует внутренние Core repository adapters и не открывает `knowledge.db`.

Публичный ContextView минимален и не раскрывает фазу, evidence count, внутренние scores, rationale или source atom IDs.
