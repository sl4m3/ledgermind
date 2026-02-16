# agent-memory-core v2.0.1

A universal long-term memory module for AI agents featuring guaranteed integrity, epistemic modeling, and high-performance hybrid storage.

## 🌟 Major Features

- **Enterprise-Ready Storage**: Support for **PostgreSQL** and **pgvector** as alternatives to SQLite, enabling sub-second search across millions of records.
- **Privacy & Compliance**: Built-in PII Masking and Encryption at Rest (Fernet) for sensitive memory content.
- **Epistemic Reasoning Engine**: Features dedicated engines for **Reflection**, **Distillation**, and **Recursive Truth Resolution**.
- **Distributed Synchronization**: Real-time multi-instance sync via **Redis Pub/Sub**.
- **Zstandard Compression**: Significant storage savings for vectors and text content.
- **Performance Optimized**: Conflict detection via $O(1)$ database indices and intelligent mtime-based integrity caching.

## 🛡 Integrity & Reliability Guarantees

- **Hybrid Semantic Store**: High-performance metadata indexing in SQLite/Postgres combined with Git-backed storage for immutable audit logs.
- **ACID-compliant Transactions**: Atomic multi-operation support with automatic rollback on failure.
- **Proactive Validation**: All architectural invariants are validated via `IntegrityChecker` before any change is committed.
- **Recursive Truth Resolution**: Hybrid search automatically follows the knowledge evolution graph to return the latest active version of any fact.

## 🚀 Advanced Reasoning

- **Epistemic Reflection**: A hypothesis-driven model that reviews memories to detect patterns and contradictions.
- **Procedural Distillation**: Extraction of SOPs (Standard Operating Procedures) from successful episode trajectories.
- **Git History Indexing**: Learns from human code commit history to enrich agent context.

## ⚡ Quick Start

```python
from agent_memory_core.api.memory import Memory

# Initialization with hybrid storage
memory = Memory(storage_path="./my_agent_memory")

# Recording a decision
memory.record_decision(
    title="Use PostgreSQL with pgvector",
    target="architecture/storage",
    rationale="Need sub-second semantic search across 1M+ records"
)

# Hybrid search with Recursive Truth Resolution
results = memory.search_decisions("high-scale storage options", mode="balanced")
```

## Installation
```bash
pip install -e ./core
```
