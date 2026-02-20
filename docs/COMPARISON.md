# Comparison with Alternatives

How LedgerMind compares to other AI memory frameworks.

---

## Feature Matrix

| Feature | LedgerMind | LangChain Memory | Mem0 | Zep |
|---|---|---|---|---|
| **Primary goal** | Knowledge lifecycle management | Session context | Personalization | Fast retrieval |
| **Storage** | SQLite + Git (hybrid) | Varies (Redis, SQL) | Vector DB | Postgres + Vector |
| **Knowledge versioning** | Explicit DAG (supersede) | None | Partial | None |
| **Audit trail** | Cryptographic (Git commits) | Application logs | Metadata only | Metadata only |
| **Truth resolution** | Recursive (follows DAG) | Similarity / Last-write | Similarity | Similarity / Recency |
| **Integrity invariants** | Formal (ConflictEngine) | Basic schema | None | Basic schema |
| **Reasoning layer** | Reflection + Distillation | Manual | None | Auto-summarization |
| **Autonomous maintenance** | Yes (BackgroundWorker) | No | No | No |
| **Conflict detection** | Multi-level (3 layers) | None | None | None |
| **Self-healing** | Yes (stale lock removal, meta-sync) | No | No | No |
| **MCP compatible** | Yes (15 tools) | No | No | No |
| **REST + WebSocket** | Yes | No | No | Limited |
| **Epistemic model** | Yes (proposals, falsification) | No | No | No |
| **Git-native** | Yes (commits as audit log) | No | No | No |
| **Prometheus metrics** | Yes | No | No | Limited |

---

## When to Choose LedgerMind

### Choose LedgerMind when:

- **You need audit and traceability.** Every decision change creates a Git commit. You can always answer "who changed this, when, and why."
- **Your agent must not repeat mistakes.** The Reflection Engine detects recurring failures and formalizes prevention rules autonomously.
- **Knowledge conflicts are a concern.** Two agents recording contradictory decisions about the same component will trigger a conflict error — not silent overwrite.
- **You want autonomous evolution.** The system generates, evaluates, and promotes its own improvement proposals without human intervention.
- **You are building long-running autonomous agents.** The decay system ensures stale knowledge is automatically retired, keeping the knowledge base fresh.

### Choose an alternative when:

- **You need simple session memory.** For short-lived conversations where you just need recent context, LangChain's `ConversationBufferMemory` is simpler.
- **You only need semantic search over facts.** If you just want to store and retrieve facts without lifecycle management, Mem0 or Chroma are lighter-weight.
- **Latency is critical and you have simple needs.** Zep is optimized for sub-millisecond retrieval without the overhead of conflict detection.

---

## Key Differentiators

### 1. Knowledge as a DAG, Not a Flat Store

Most systems treat memory as a flat key-value or vector store. When knowledge changes, the old record is overwritten or a new one is added without linkage.

LedgerMind treats knowledge as a **directed acyclic graph of truth**. When a decision changes:
- The old record gets `status=superseded` + a forward pointer (`superseded_by`)
- The new record gets a backward pointer (`supersedes`)
- Search follows this chain automatically to return the current truth

This means you can always recover the full history of any piece of knowledge.

### 2. Epistemic Safety Through Falsification

Other systems promote information to "memory" as soon as it appears. LedgerMind's Reflection Engine applies scientific falsification: a hypothesis (Proposal) must pass through an observation window and achieve sufficient confidence before it becomes an active Decision.

Contradictory evidence (successes in an error cluster) reduces confidence and can falsify a hypothesis entirely — preventing the agent from committing to a wrong conclusion.

### 3. Three-Layer Conflict Protection

No other framework we are aware of enforces conflict invariants at the database level. LedgerMind checks for conflicts at three points:
1. Before the transaction starts (pre-flight)
2. Before entering the filesystem lock (pre-transaction)
3. Inside the lock (inside-transaction, guards against race conditions)

This makes it safe to run multiple agents writing to the same memory store concurrently.

### 4. Git as the Audit Backend

Using Git as the audit log is unusual but powerful. It provides:
- Cryptographic integrity (SHA hashes)
- Branching capability for experimental knowledge
- Standard tooling for reviewing changes (`git log`, `git diff`)
- Offline-first operation

---

## Migration from Other Systems

### From LangChain Memory

LangChain's conversation memory is session-scoped and lacks structure. To migrate:

1. Export your important decisions from LangChain session summaries
2. Use `record_decision()` with a meaningful `target` for each
3. Replace `ConversationBufferMemory` context retrieval with `get_context_for_prompt()`

### From Mem0

Mem0 stores flat facts. To migrate:

1. Export all facts from Mem0
2. Group them by domain (target)
3. Import each group as a `decision` or `assumption` into LedgerMind
4. Replace Mem0's `search()` with `search_decisions(mode="strict")`
