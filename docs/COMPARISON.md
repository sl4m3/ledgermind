# Comparison with Alternatives

This document provides a technical comparison between the Ledgermind and other popular memory frameworks for AI agents.

| Feature | Ledgermind | LangChain Memory | Mem0 (EmbedChain) | Zep |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Goal** | Knowledge Governance & Audit | Session Context Management | User Personalization | High-Performance Search |
| **Storage Engine** | Hybrid (SQLite + Git) | Pluggable (Redis, SQL, etc.) | Vector Databases | Postgres + Vector |
| **Versioning** | Explicit DAG (Supersede) | None (usually overwrite) | Partial (Update) | None |
| **Audit Trail** | Cryptographic (Git commits) | Application Logs | Metadata | Metadata |
| **Truth Resolution** | Recursive (follows DAG) | Most Recent / Similarity | Similarity | Similarity / Recency |
| **Integrity Checks** | Formal Invariants (I1-I7) | Basic Schema | None | Basic Schema |
| **Reasoning** | Reflection & Distillation | None (Manual) | None | Automated Summarization |

## Why Ledgermind?

### 1. Hardened Auditability
Unlike LangChain or Mem0, where memory can be overwritten or deleted, our system uses **Git as a back-end**. Every change is a commit. You can always answer: *"Who changed this rule, when, and based on what evidence?"*

### 2. Knowledge Evolution vs. Data Storage
Most systems treat memory as a simple key-value store or a vector index. Ledgermind treats it as an **evolving graph of truths**. Using the `supersede` operation, agents can replace old SOPs with new ones while maintaining a link to the original reasoning.

### 3. Recursive Truth Resolution
When an agent searches for "deployment policy", other systems might return an outdated version if it's more semantically similar. Our system's **Hybrid Search** automatically follows the supersession chain to return the currently `active` version, guaranteed.

### 4. Epistemic Safety
With the **Reflection Engine**, the system distinguishes between *facts* and *hypotheses*. It requires a "Review Window" and "Evidence Threshold" before a hypothesis can be promoted to a decision, preventing "hallucination loops."
