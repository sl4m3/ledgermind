# ledgermind-core

Закрытое ядро LedgerMind 4.0. Текущий Python-пакет сохраняется как переходный reference backend до завершения Rust cutover.

## Граница закрытого Rust Core

- Core работает отдельным процессом и общается с Local только через versioned IPC по stdin/stdout.
- Core владеет собственной SQLite-базой `knowledge.db` и всеми её SQL-миграциями внутри storage crate.
- Local владеет отдельной `rounds.db`; Core никогда её не открывает.
- Core получает Hypothesis, но не RawRound, не вызывает модели и не имеет HTTP/TLS/DNS/cloud-клиентов.
- Domain/application crates не содержат SQL; SQL находится только в Rust storage crate.
