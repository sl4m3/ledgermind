# Agent Memory Core (v2.1.1)

A universal long-term memory module for AI agents featuring guaranteed integrity, epistemic modeling, and high-performance hybrid storage (SQLite + Git).

## 🌟 Core Features

- **Hybrid Semantic Store**: Combines the speed of SQLite metadata indexing with the auditability of Git cold storage.
- **Epistemic Reasoning Engine**: Features dedicated engines for **Reflection**, **Distillation**, and **Recursive Truth Resolution**.
- **Conflict Management**: Identifies and prevents contradictory decisions at the architectural level.
- **ACID-compliant Transactions**: Atomic multi-operation support with automatic rollback on failure.
- **Git History Indexing**: Synchronizes project Git history into agent episodic memory.

## 🛡 Reliability Guarantees

- **Invariant Enforcement**: All architectural rules are validated via `IntegrityChecker` before any change is committed.
- **Recursive Truth Resolution**: Automatically follows the knowledge evolution graph to return the latest active version of any fact.
- **Traceable History**: Every memory change results in a Git commit, providing a permanent, non-repudiable audit trail.

## ⚡ Quick Start

```python
from agent_memory_core.api.memory import Memory

# Initialization with SQLite/Git storage
memory = Memory(storage_path="./my_agent_memory")

# Recording a decision
memory.record_decision(
    title="Use SQLite for metadata",
    target="architecture/storage",
    rationale="Need a portable, local-first metadata index."
)

# Search with Recursive Truth Resolution
results = memory.search_decisions("metadata storage options")
```

## Installation
```bash
pip install -e ./core
```
