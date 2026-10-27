# ADR 0005: Local executes Core-owned tasks

- **Статус:** accepted
- **Дата:** 2026-08-14

Core/Application is the semantic owner of a RawRound. It owns normalization,
claims, MemoryObject identity, Target/applicability, Facet, Conditions,
Merge/Replace, provenance, lineage, and Control decisions. Core persists
durable generic execution tasks through the IPC boundary.

Local owns provider transport, secrets, generation/embedding HTTP, leases,
process lifecycle, retry/telemetry, and the Local `rounds.db`. It polls the
opaque task payload, performs the configured provider call, and returns the
result. Local does not interpret a result as a HypothesisRecord or decide a
semantic outcome. Integrations only capture RawRound and runtime context.

This supersedes ADR 0001 and ADR 0003. The stable IPC contract is retained;
the change is ownership of semantic interpretation, not a new model call or
database schema.
