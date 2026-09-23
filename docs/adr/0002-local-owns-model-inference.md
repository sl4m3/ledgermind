# ADR 0002: Local владеет модельными вызовами

- **Статус:** accepted
- **Дата:** 2026-08-03

Все вызовы моделей выполняет Local через конфигурируемый `InferenceBroker`.
Пользователь выбирает OpenAI-совместимый endpoint, модель и профиль обработки.

Секреты принадлежат Local secret store, адресуются через `secret_ref` и не передаются в Core, Integrations, RawRound или обычные журналы.
Integrations не вызывает модели.
