# ADR-001 (refactor workspace)

## Context

The legacy repository has been preserved as a historical snapshot in
`.refactor-workspace/ledgermind-core-legacy-dump`. It is not an input to the
current service and is not automatically migrated.

## Decision

The current `ledgermind-core` is a closed Rust process with a narrow IPC boundary.
The historical Python package is not part of the runtime or package delivery.

The closed Core owns SQLite `knowledge.db` inside its private data directory and
applies its own migrations. SQL is limited to the Rust storage crate; domain and
application code remain infrastructure-independent.

`ledgermind_local` owns a separate `rounds.db` and may use only the public Core
IPC boundary. Core never opens `rounds.db`, receives `RawRound`, calls models, or
uses HTTP/TLS/DNS/cloud clients.

Versions v3 and v4 are incompatible. The current architecture starts from
RawRound v2 and deliberately provides no v3 migration or compatibility path.
