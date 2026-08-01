# ADR-001 (refactor workspace)

## Context

The legacy v3 repository has been preserved as a snapshot in
`.refactor-workspace/ledgermind-core-legacy-dump`.

## Decision

`ledgermind-core` is a clean, infrastructure-free core module.
It must not depend on Hermes, MCP, SQLite, filesystem paths, git, vector model runtimes,
or projection workers.

`ledgermind_local` is implemented separately and may depend on `ledgermind-core`.
