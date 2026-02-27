# Changelog

All notable changes to the LedgerMind project since version 2.0.0.

---

## [v3.0.0] - 2026-02-27

- **DecisionStream Lifecycle Engine:** Autonomous phases (`PATTERN`, `EMERGENT`, `CANONICAL`) with temporal signal analysis.
- **Procedural Distillation (MemP):** Automatic conversion of successful trajectories into step-by-step instructions.
- **Zero-Touch Hooks Pack:** Transparent memory operations for Gemini CLI, Claude Code, Cursor, and VS Code.
- **Security Hardening:** Path traversal protection and absolute path validation in ProjectScanner.
- **Transaction Integrity:** SAVEPOINT support and thread-local isolation for concurrent operations.
- **Self-Healing Index:** Automatic reconstruction of SQLite metadata from Markdown source files.

## [v2.8.7] - 2026-02-26

**Critical Patch & Security Hardening**

### Fixed
- **Git Audit:** Fixed a critical bug in `GitAuditProvider` where interaction 
  events were not being added to the Git commit history.
- **Security:** Patched path traversal vulnerability in `ProjectScanner` 
  and arbitrary file write in `MemoryTransferManager`.
- **Search Optimization:** Batch metadata fetches in `search_decisions` 
  to reduce SQLite overhead by 40%.
- **Integrity:** Optimized `sync_meta_index` with batch transactions.

### Added
- **API Validation:** Comprehensive unit tests for API contract models 
  and schemas.
- **Core Logic:** Optimized `resolve_to_truth` using recursive Common 
  Table Expressions (CTE) for deep inheritance.

---

## [v2.8.6] - 2026-02-26

**Performance & Context Optimization**

### Added
- **Branding:** Replaced Mermaid-based architecture diagrams with high-fidelity 
  SVG (`core-arc.svg`) for better README rendering.
- **Storage:** Enforced standardized storage paths outside project root for 
  better isolation.

### Changed
- **Search:** Optimized `search_decisions` by deferring JSON parsing 
  until after the ranking phase.

---

## [v2.8.5] - 2026-02-26

**Stability & Semantic Enrichment**

### Added
- **Semantic Boosting:** Implemented keyword-based enrichment and 
  status-based search boosting (active vs. superseded).
- **Bridge API:** Enhanced context injection with file paths and explicit 
  instructions for the agent.

### Fixed
- **CI/CD:** Fixed semantic search tests by pre-seeding memory in the 
  test environment.
- **Hooks:** Aligned Gemini CLI hooks with the latest JSON I/O protocol.

---

## [v2.8.4] - 2026-02-26

**VS Code Hardcore Zero-Touch**

### Added
- **VS Code Extension:** Implemented "Hardcore Zero-Touch" mode for 
  seamless project bootstrapping within VS Code.
- **Retrieval:** Optimized Jina v5 Nano retrieval and hardened episodic 
  recording logic.

---

## [v2.8.3] - 2026-02-25

**Search Stability & DB Locking**

### Fixed
- **Storage:** Fixed critical database locking issues during high-speed 
  semantic searches.
- **Transactions:** Enhanced `TransactionManager` to handle 
  nested SAVEPOINTS with thread-local isolation.

---

## [v2.8.2] - 2026-02-25

**Probabilistic Reflection & Distillation**

### Added
- **Reflection:** Transitioned from binary success/failure to a 
  probabilistic model with float weights.
- **Distillation:** Successful trajectories are now distilled into 
  `procedural.steps` for procedural proposals.

---

## [v2.8.1] - 2026-02-24

**Zero-Touch Refinement**

### Fixed
- **CLI:** Added missing imports and threshold support in `bridge-context`.
- **Bridge:** Enhanced injection policy and automated arbitration for 
  conflicting memories.

---

## [v2.8.0] - 2026-02-24

**Zero-Touch Automation & Client Hooks**

### Added
- **Zero-Touch:** Initial release of the Bridge API for low-latency 
  context injection.
- **Hooks Pack:** Official support for Gemini CLI, Claude Desktop, 
  and Cursor.

---

## [v2.7.8] - 2026-02-24

**Branding & Distribution**

### Added
- **Distribution:** Initial PyPI publishing workflow.
- **Branding:** Social banners and comparison tables added to README.

---

## [v2.7.7] - 2026-02-24

**Security & SSE Stability**

### Fixed
- **SSE:** Mocked `EventSourceResponse` in tests to prevent hangs.
- **Background Worker:** Fixed crash in mock worker during verification tests.

### Added
- **Security:** Protected SSE/WS endpoints and hardened Dockerfile.

---

## [v2.7.6] - 2026-02-24

**FTS5 Stability & Latency Optimization**

### Fixed
- **FTS5:** Enhanced keyword search indexing with automatic re-sync.
- **Performance:** Optimized write latency and vector search speed.

---

## [v2.7.4] - 2026-02-23

**Evolution Proposals & Reflection**

### Added
- **Proposals:** Introduced `ProceduralProposals` for automated 
  workflow discovery.
- **Reflection:** Enhanced logic for clustering events into 
  semantically related trajectories.

---

## [v2.7.3] - 2026-02-23

**Concurrency & Integrity**

### Fixed
- **Integrity:** Resolved I4 integrity violations (single active decision) 
  in high-concurrency environments.
- **Thread Safety:** Implemented `thread-local` storage for transactions.

---

## [v2.7.1] - 2026-02-23

**Multi-Agent Namespacing & Security**

### Added
- **Namespacing:** Support for logical partitioning via the 
  `namespace` parameter.
- **Webhooks:** Async HTTP notifications for memory events.
- **Jina v5 Nano:** Integrated Jina v5 Nano for high-efficiency 
  on-device embeddings.

---

## [v2.6.3] - 2026-02-22

**Deduplication & Bridge API**

### Added
- **Deduplication:** Sliding window context deduplication in search results.
- **FTS5 Fallback:** Implemented keyword search fallback for non-vector 
  environments.

---

## [v2.6.0] - 2026-02-20

**Autonomous Background Worker**

### Added
- **Background Worker:** Heartbeat system for autonomous maintenance 
  (self-healing, reflection, decay).
- **Target Registry:** Canonical name normalization and alias resolution.
- **Conflict Resolution:** Intelligent resolution engine for semantic collisions.

---

## [v2.4.3] - 2026-02-17

**UTF-8 & Schema Evolution**

### Added
- **UTF-8:** Full support for UTF-8 input in interactions and decisions.
- **Schema:** Refined context injection schema for better multi-client 
  compatibility.

---

## [v2.4.1] - 2026-02-17

**Anti-Spam & Proactive Reflection**

### Added
- **Cooldown:** Knowledge cooldown (TTL) to prevent interaction loops.
- **Reflection:** Proactive extraction of best practices from successful 
  interaction trajectories.

---

## [v2.4.0] - 2026-02-17

**Unified Versioning & TUI Stability**

### Added
- **Unified Stack:** Core, MCP Server, and Runner consolidated into a 
  single version track.
- **Vector Search:** Reliable 4-bit GGUF support for cosine similarity 
  ranking.

---

## [v2.2.1] - 2026-02-17

**Dynamic Context Steering**

### Added
- **Steering:** Initial support for dynamic context steering based on 
  agent intent analysis.

---

## [v2.1.0] - 2026-02-17

**Universal Runner & Governance**

### Added
- **PTY Runner:** Universal PTY-based execution environment for 
  governed memory access.
- **Security:** Level 2 Memory Governance with TTY noise filtering.

---

## [v2.0.0] - 2026-02-16

**The Hybrid Memory Era**

### Added
- **Hybrid Storage:** Complete rewrite to use SQLite (indexing) + 
  Git (versioning/audit).
- **Privacy Controls:** Fine-grained access control for memory artifacts.
- **REST Gateway:** Initial release of the REST-to-MCP bridge.
- **Auto-Migration:** Automatic migration from v1.x flat-file storage.
