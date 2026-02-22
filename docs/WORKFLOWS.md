# Workflows

This document walks through the most common usage patterns in LedgerMind with full step-by-step explanations of what happens inside the system.

---

## Workflow 1: Basic Decision Recording and Retrieval

**Scenario:** An agent analyzes a codebase and records a framework choice.

```python
from ledgermind.core.api.memory import Memory

memory = Memory(storage_path="./memory")

# Step 1: Record a decision
result = memory.record_decision(
    title="Use FastAPI for the web layer",
    target="web_framework",
    rationale="FastAPI provides high performance and automatic OpenAPI generation, "
              "which is critical for our microservices architecture.",
    consequences=["Install fastapi and uvicorn", "Update all HTTP handler signatures"]
)

print(result.metadata["file_id"])
# -> decisions/2024-02-01_web_framework_a1b2c3.md

# Step 2: Search for it later
results = memory.search_decisions("Which web framework are we using?", mode="strict")
for r in results:
    print(f"{r['title']} | score={r['score']:.2f}")
# -> Use FastAPI for the web layer | score=0.94
```

**What happens internally:**
1. `TargetRegistry.normalize("web_framework")` — no alias found, returns as-is
2. `TargetRegistry.register("web_framework")` — saves to `targets.json`
3. `semantic.list_active_conflicts("web_framework")` — empty, no conflicts
4. `process_event()` → `router.route()` → `store_type = "semantic"`
5. `semantic.transaction()` acquires `FileSystemLock`
6. `semantic.save()` writes the `.md` file and makes a Git commit
7. `vector.add_documents()` indexes `title + rationale` as an embedding
8. `episodic.append(event, linked_id=file_id)` creates an immortal link
9. `MemoryDecision(should_persist=True, metadata={"file_id": "..."})` returned

---

## Workflow 2: Auto-Supersede (Intelligent Update)

**Scenario:** The decision about a framework evolves. No need to find the old ID manually.

```python
# The "Use FastAPI" decision already exists for target="web_framework"

# Just call record_decision again for the same target
result = memory.record_decision(
    title="Upgrade FastAPI: switch to Pydantic v2",
    target="web_framework",
    rationale="Pydantic v2 delivers a 5-10x validation speedup. "
              "Migration is straightforward with the compatibility layer."
)
# ✓ No ConflictError raised — system handled it automatically
```

**Internal auto-supersede chain:**
1. `semantic.list_active_conflicts("web_framework")` → `["decisions/..._web_framework_a1b2c3.md"]`
2. `vector_available = True` → encode new text: `title + rationale`
3. `cosine_similarity(new_vec, old_vec)` → `0.91 > 0.85` threshold
4. `supersede_decision()` called automatically with the old ID
5. Old record: `status=superseded`, `superseded_by=new_file_id`
6. New record: `status=active`, `supersedes=[old_file_id]`
7. Git history shows both commits, linked via frontmatter

---

## Workflow 3: Explicit Supersede (Paradigm Shift)

**Scenario:** The team decides to migrate the entire web layer from Python to Go.

```python
# Find the old decision ID using audit mode (returns all statuses)
old_results = memory.search_decisions("FastAPI web framework", mode="audit")
old_id = old_results[0]["id"]

# Explicit supersede
memory.supersede_decision(
    title="Migrate web layer to Go (Gin framework)",
    target="web_framework",
    rationale="Go's goroutine model is required to achieve sub-10ms latency "
              "at 100k+ RPS. The FastAPI rewrite would not meet these targets.",
    old_decision_ids=[old_id],
    consequences=[
        "Team must complete Go training by Q3",
        "All HTTP handlers must be rewritten in Gin",
        "Update CI/CD pipeline to build Go binaries"
    ]
)
```

**When to use explicit vs auto-supersede:**
- **Auto:** Same technology, incremental improvement, similar rationale text
- **Explicit:** Technology migration, paradigm change, or when you want explicit traceability

---

## Workflow 4: Reflection Cycle — From Errors to Rules

**Scenario:** An agent encounters repeated Redis connection failures. The system generates diagnostic proposals.

```python
from ledgermind.core.api.bridge import IntegrationBridge

bridge = IntegrationBridge(memory_path="./memory")

# Agent encounters several errors
bridge.record_interaction(
    "Connect to Redis cache", "ConnectionRefusedError: [Errno 111]", success=False
)
bridge.record_interaction(
    "Write to Redis session store", "redis.exceptions.ConnectionError: Connection refused", success=False
)
bridge.record_interaction(
    "Redis health check", "Error: ECONNREFUSED 127.0.0.1:6379", success=False
)

# Trigger reflection (automatic in MCP mode every 4 hours)
proposal_ids = bridge.memory.run_reflection()
print(f"Generated {len(proposal_ids)} proposals")
```

**What the ReflectionEngine does:**
1. Clusters events by `target` — errors targeting "redis" form a cluster
2. `errors (3) >= error_threshold (1)` → triggers hypothesis generation
3. Two competing proposals are created:
   - **H1 "Structural flaw in redis"** — `confidence=0.5`, posits a logical config error
   - **H2 "Environmental noise in redis"** — `confidence=0.4`, posits transient failures
4. H1 and H2 are cross-linked via `alternative_ids`
5. On next cycle, if more errors → H1 confidence rises
6. If a successful Redis operation appears → H1 confidence drops (falsification)
7. When H1 reaches `confidence ≥ 0.9` and `ready_for_review=True` and `objections=[]` → **auto-accepted**

---

## Workflow 5: Git History Synchronization

**Scenario:** Keep memory in sync with actual code evolution.

```python
# Index the last 30 commits from the current repository
indexed = memory.sync_git(repo_path=".", limit=30)
print(f"Indexed {indexed} commits")

# Commits with conventional format (e.g. "fix(redis): handle timeout")
# are automatically parsed: target="redis", kind="commit_change"
# The ReflectionEngine will pick these up in its next cycle
```

In MCP mode, this runs automatically every 5 minutes via `BackgroundWorker._run_git_sync()` (last 5 commits).

---

## Workflow 6: Context Injection into Agent Prompts

**Scenario:** Inject relevant memory into every LLM call.

```python
from ledgermind.core.api.bridge import IntegrationBridge

bridge = IntegrationBridge(memory_path="./memory", relevance_threshold=0.35)

user_input = "How should we configure the database connection pool?"

# Retrieve relevant context
context_block = bridge.get_context_for_prompt(user_input, limit=3)

# Build the full prompt
if context_block:
    full_prompt = f"{context_block}\n\n---\n\nUser: {user_input}"
else:
    full_prompt = f"User: {user_input}"

# Call your LLM
response = call_llm(full_prompt)

# Record the interaction for future reflection
bridge.record_interaction(user_input, response, success=True)
```

The `context_block` looks like:
```
[LEDGERMIND KNOWLEDGE BASE ACTIVE]
{
  "source": "ledgermind",
  "memories": [
    {
      "id": "decisions/database_abc.md",
      "title": "Use PostgreSQL with asyncpg",
      "target": "database",
      "kind": "decision",
      "score": 0.876,
      "recency": "2024-02-01T12:00:00",
      "content": "### Use PostgreSQL with asyncpg\n**Rationale:** ..."
    }
  ]
}
```

---

## Workflow 7: Proposal Review and Acceptance

**Scenario:** A human reviews auto-generated proposals before they become decisions.

```python
# Find all draft proposals
results = memory.search_decisions("", mode="audit")
drafts = [r for r in results if r["kind"] == "proposal" and r["status"] == "draft"]

for d in drafts:
    print(f"[{d['score']:.2f}] {d['title']} (target: {d['target']})")

# Review a specific proposal
import os
from ledgermind.core.stores.semantic_store.loader import MemoryLoader

path = os.path.join(memory.semantic.repo_path, drafts[0]["id"])
with open(path) as f:
    data, body = MemoryLoader.parse(f.read())
    ctx = data["context"]
    print(f"Confidence: {ctx['confidence']}")
    print(f"Strengths: {ctx['strengths']}")
    print(f"Objections: {ctx['objections']}")

# Accept it
decision = memory.accept_proposal(drafts[0]["id"])
print(f"Accepted → {decision.metadata['file_id']}")

# Or reject it
memory.reject_proposal(drafts[0]["id"], reason="Not enough evidence yet.")
```

---

## Workflow 8: Export and Restore Memory

**Scenario:** Migrate memory to another machine or create a checkpoint.

```python
from ledgermind.core.api.transfer import MemoryTransferManager

# Export
transfer = MemoryTransferManager(storage_path="./memory")
archive = transfer.export_to_tar("memory_backup_2024-02-01.tar.gz")
print(f"Exported to: {archive}")

# Restore on another machine
transfer2 = MemoryTransferManager(storage_path="./restored")
transfer2.import_from_tar("memory_backup_2024-02-01.tar.gz", restore_path="./restored")

# Verify
from ledgermind.core.api.memory import Memory
restored = Memory(storage_path="./restored")
print(f"Restored {len(restored.get_decisions())} decisions")
```

---

## Workflow 9: Knowledge Graph Visualization

**Scenario:** Visualize how a specific area of knowledge has evolved.

```python
# Full graph
mermaid = memory.generate_knowledge_graph()

# Filtered to one area
mermaid_db = memory.generate_knowledge_graph(target="database")

print(mermaid_db)
# graph LR
#   A["decisions/database_v1.md<br/>Use PostgreSQL"] -->|superseded_by| B
#   B["decisions/database_v2.md<br/>Use Aurora PostgreSQL"]
#   E1([episodic:42]) -.->|evidence| A
#   E2([episodic:87]) -.->|evidence| B
```

Paste the output into [mermaid.live](https://mermaid.live) or any Markdown renderer that supports Mermaid.

---

## Workflow 10: Decay and Maintenance

**Scenario:** Regular system housekeeping.

```python
# Preview what would be cleaned
preview = memory.run_decay(dry_run=True)
print(f"Would archive: {preview.archived} episodic events")
print(f"Would prune:   {preview.pruned} old episodic events")
print(f"Would forget:  {preview.semantic_forgotten} semantic records")
print(f"Immortal (retained): {preview.retained_by_link}")

# Apply
report = memory.run_decay(dry_run=False)

# Full maintenance (includes integrity check + duplicate scan)
maintenance = memory.run_maintenance()
print(maintenance)
# {
#   "decay": {"archived": 12, "pruned": 5, ...},
#   "merging": {"proposals_created": 0, "ids": []},
#   "integrity": "ok"
# }
```

**Decay rules summary:**
- Episodic events with `linked_id` → **never deleted** (Immortal Link)
- Episodic events older than `ttl_days` → archived, then pruned
- Semantic proposals → confidence drops 5% per week of inactivity
- Semantic decisions/constraints → confidence drops ~1.67% per week
- Any record with `confidence < 0.1` → `forget()` (hard delete)
These decay rules keep the knowledge base focused and reliable over long durations.


