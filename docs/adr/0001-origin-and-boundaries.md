# ADR-001 (refactor workspace)

## Context

The legacy repository has been preserved as a historical snapshot in
`.refactor-workspace/ledgermind-core-legacy-dump`. It is not an input to the
current service and is not automatically migrated.

## Decision

`ledgermind-core` is a clean, infrastructure-free core module.
It must not depend on Hermes, MCP, SQLite, filesystem paths, git, vector model runtimes,
or projection workers.

`ledgermind_local` is implemented separately and may depend on `ledgermind-core`.

Versions v3 and v4 are incompatible. The current architecture starts from
RawRound v2 and deliberately provides no v3 migration or compatibility path.
