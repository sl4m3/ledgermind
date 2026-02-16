# agent-memory-core v2.0.0

A universal long-term memory module for AI agents featuring guaranteed integrity, epistemic modeling, and hybrid storage.

## 🌟 New in v2.0.0

- **Privacy Controls**: Built-in PIIMasker for PII protection and optional Encryption at Rest via Fernet.
- **Auto-Migration Engine**: Automatically upgrades data structure and SQLite schema on startup.
- **Vector Optimization**: Integrated Zstandard compression and embedding caching.
- **Improved Recovery**: Automatic reconciliation of untracked files after system crashes.

## 🛡 Integrity & Reliability Guarantees

- **Structured Ranking Policy**: Formalized ranking policy for hybrid search. Vector similarity is adjusted with bonuses for "Active" status (Truth Bias), source authority (Human > Agent), and penalties for obsolescence (Superseded/Deprecated). This ensures the agent always receives the most relevant and *active* information.
- **Boundary Enforcement**: Strict validation of input data and business rules at the API boundary. Invalid operations (violating invariants I1-I7) are rejected with explicit exceptions (`ConflictError`, `InvariantViolation`), protecting the store from incorrect client calls.
- **Hybrid Semantic Store**: A two-tier storage architecture. SQLite provides ACID transactions and instant metadata invariant checks, while Git serves as a reliable append-only log for audit and content versioning.
- **ACID-compliant Transactions**: Support for atomic multi-file operations via `SemanticStore.transaction()`. Changes are either fully applied (commit) or automatically rolled back (rollback) upon failure. A WAL-like mechanism is used for filesystem recovery.
- **Proactive Validation**: All architectural invariants are validated (`IntegrityChecker`) **BEFORE** changes are committed to Git and SQLite.
- **Robust Locking**: Cross-platform (`fcntl`-based) file locking ensures safety during parallel operation by multiple agents.
- **Recursive Truth Resolution**: Hybrid search automatically follows knowledge supersession chains. The agent always receives the current "truth," even if the initial search hit an outdated version.

## 🚀 Core Features (Reasoning v5)

- **Epistemic Reflection & Falsification**: Next-generation reflection system building a scientific hypothesis model:
    - **Competing Hypotheses**: For each error pattern, alternative explanations (logic failure vs. external noise) are generated and compete for confidence.
    - **Scientific Falsification**: The system actively seeks refutations. Any success in the context of an error hypothesis reduces its weight until it is potentially falsified.
    - **Bayesian-ish Confidence**: Confidence is calculated based on the balance of supporting and refuting evidence.
    - **Structured Scrutiny**: Proposals contain explicit `strengths` and `objections` for transparent auditing.
- **Procedural Distillation (MemP)**: Automatic extraction of procedural knowledge (SOPs) from successful event chains (trajectories).
- **Git History Indexing**: Enriching memory with knowledge from human code commit history.
- **Knowledge Evolution**: A rigorous process for replacing old knowledge with new information via a DAG structure.

## 🛠 Architecture

- **Semantic Store**: Markdown files with metadata in SQLite. The repository for "truths" and rules.
- **Episodic Store**: SQLite database for the event stream (append-only log).
- **Vector Store**: Index for fast candidate retrieval based on semantic similarity.
- **Reasoning Engines**: Reflection, Conflict, Distillation, Decay.

## ⚡ Quick Start

```python
from agent_memory_core.api.memory import Memory

# Initialization with hybrid storage
memory = Memory(storage_path="./my_agent_memory")

# Recording a decision
memory.record_decision(
    title="Use PostgreSQL",
    target="database",
    rationale="Need ACID and vertical scaling for initial phase"
)

# Hybrid search with Recursive Truth Resolution
results = memory.search_decisions("How to store structured data?", mode="balanced")
```
