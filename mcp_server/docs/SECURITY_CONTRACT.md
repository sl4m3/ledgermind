# Security Contract: Agent Memory System

This document defines the security guarantees provided by the system and the responsibilities of the user/integrator.

## 1. System Guarantees (The "Promises")

### G1: Non-Repudiation
Every change to the Semantic Memory is recorded in a Git repository. Provided the `.git` directory is protected, the history of decisions is immutable and verifiable.

### G2: Authority Isolation
The system guarantees that an entity with `agent` role cannot supersede or modify any decision created by a human (identified by the absence of the `[via MCP]` tag).

### G3: Invariant Enforcement
The system guarantees that no operation will be committed if it results in an inconsistent state (e.g., knowledge cycles or multiple active truths for the same target). This is enforced via proactive `IntegrityChecker` runs during transactions.

### G4: Transactional Atomicity
Multi-step operations (like `supersede_decision`) are atomic. Either all changes (new file creation + old file status update) are committed, or none are.

### G5: Auditability
All tool invocations through the MCP layer are recorded in a separate `audit.log` with success/failure status and role metadata.

## 2. User Responsibilities (The "Requirements")

### R1: Secret Management
The user is responsible for keeping `AGENT_MEMORY_SECRET` secure. If compromised, an attacker can gain `agent` or `admin` privileges.

### R2: Physical Access Control
The system assumes the local filesystem where memory is stored is secure. The system does not protect against an attacker with direct write access to the `.md` files or the `.git` directory.

### R3: Review Window Monitoring
The system enforces a 1-hour "Review Window" (PI1) for AI-generated proposals. It is the user's (Admin's) responsibility to review these proposals before accepting them.

### R4: Embedding Provider Trust
The system relies on an external Embedding Provider. The user must ensure the provider is trusted, as adversarial embeddings could theoretically influence search results.

## 3. Compliance & Auditing
To perform a security audit of the memory:
1.  Check `git log --patch` for all changes.
2.  Review `audit.log` for access patterns.
3.  Run `agent-memory-mcp export-schema` to verify contract integrity.
