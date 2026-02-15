# Threat Model: Agent Memory Ecosystem

This document identifies potential security threats to the Agent Memory system and describes mitigation strategies.

## 1. System Components & Boundaries
- **Core**: Trusted domain logic. Responsible for data integrity and invariant enforcement.
- **Semantic Store (Git)**: Persistent storage. Trusted only if access is mediated by Core.
- **MCP Server**: The primary trust boundary. Mediates communication between untrusted Agents and the Core.
- **MCP Clients (Agents)**: Untrusted or semi-trusted entities interacting with the memory.

## 2. Threat Analysis (STRIDE)

### Spoofing (Identity)
- **Threat**: An unauthorized application connects to the MCP server via stdio/network.
- **Risk**: High. Could lead to unauthorized data disclosure or modification.
- **Mitigation**: 
    - Mandatory `AGENT_MEMORY_SECRET` token for privileged roles (`agent`, `admin`).
    - Session-level roles: `viewer` (no secret), `agent` (secret required), `admin` (secret required).

### Tampering (Integrity)
- **Threat**: An Agent poisons the semantic memory with harmful rules or overwrites human decisions.
- **Risk**: High. Could hijack the future behavior of other agents or the system.
- **Mitigation**:
    - **Isolation Rule**: Agents can only supersede decisions marked with the `[via MCP]` tag. Human-authored decisions are read-only for Agents.
    - **Proactive Validation**: `IntegrityChecker` prevents commits that break system invariants (cycles, multiple active targets).
    - **ACID Transactions**: Prevents partial/corrupted writes.

### Repudiation
- **Threat**: A user or agent denies making a specific memory change.
- **Risk**: Medium. Important for audit and compliance.
- **Mitigation**:
    - **Git-backed Audit**: Every change is a commit with a timestamp and author metadata.
    - **Audit Log**: Parallel append-only `audit.log` recording role, tool, and params for every request.

### Information Disclosure
- **Threat**: An unauthorized agent reads sensitive strategic decisions.
- **Risk**: High.
- **Mitigation**:
    - RBAC enforcement at the MCP layer.
    - Search filtering based on roles (future enhancement: namespace-based isolation).

### Denial of Service
- **Threat**: An agent floods the server with write requests, causing disk exhaustion or Git lock contention.
- **Risk**: Medium.
- **Mitigation**:
    - **Rate Limiting**: Integrated cooldown (default 2s) between write operations.
    - **Locking Timeout**: OS-level file locking prevents concurrent corruption but may lead to timeouts under heavy load (mitigated by retries).

### Elevation of Privilege
- **Threat**: An agent exploits a bug to gain `admin` permissions or bypass the Review Window (PI1).
- **Risk**: High.
- **Mitigation**:
    - Strict Pydantic-based contract validation.
    - Token requirement enforced at the `serve()` entry point.
    - Separation of `agent` and `admin` logic in tool handlers.

## 3. Trust Zones
- **Human Zone**: Files in `.agent_memory/semantic` not containing the `[via MCP]` marker. Highly trusted. Read-only for MCP Agents.
- **Agent Zone**: Files marked with `[via MCP]`. Semi-trusted. Managed by Agents but verified by Core.
- **Audit Zone**: `audit.log` and Git history. Append-only.
