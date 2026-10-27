# ADR 0001: Integrations только захватывает данные

- **Статус:** accepted
- **Дата:** 2026-08-03

`ledgermind-integrations` наблюдает клиентскую систему и собирает неизменяемый полный завершённый `RawRound` с `schema_version=2`.
Адаптеры не извлекают семантику, не создают Hypothesis/Atom и не вызывают Core напрямую как библиотеку.

Интеграция может получить минимальный `ContextView` и доставить RawRound в Local или Cloud через публичный protocol.
