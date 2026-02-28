# Quick Start Tutorial

Build your first autonomous agent with LedgerMind in 5 minutes.

---

## Prerequisites

- Python 3.10 or higher
- Git installed and configured (`git config --global user.name` and `user.email`)

---

## Step 1: Install

```bash
# Vector search is included by default
pip install ledgermind
```

---

## Step 2: Initialize

```python
from ledgermind.core.api.bridge import IntegrationBridge

# This creates ../.ledgermind/ in the parent directory (outside project root)
# Placing memory one level up is the recommended standard for best isolation.
bridge = IntegrationBridge(memory_path="../.ledgermind")
memory = bridge.memory

print("✓ Memory initialized")
```

Or via CLI:
```bash
ledgermind-mcp init --path ../.ledgermind
```

---

## Step 2.5: Bootstrap Your Knowledge (Recommended for Agents)

If you are an agent entering a new project, use the **Deep Scan** tool to automatically discover the project structure and key configuration files. This report includes a **Memory Storage Policy** that ensures you record decisions correctly.

Via MCP (JSON request):
```json
{
  "tool": "bootstrap_project_context",
  "path": "."
}
```

This will provide you with a comprehensive report of the project, including a tree structure (up to 7 levels deep) and the content of all relevant `.md` and configuration files.

---

## Step 3: Record Your First Decision

```python
memory.record_decision(
    title="Use FastAPI for all REST endpoints",
    target="web_framework",
    rationale="FastAPI provides async support, automatic OpenAPI docs, "
              "and Pydantic validation out of the box.",
    consequences=[
        "Install fastapi and uvicorn[standard]",
        "All route handlers must be async functions"
    ]
)

print("✓ Decision recorded")
```

Check the Git log:
```bash
cd project_memory/semantic
git log --oneline
# a1b2c3d Add decision: Use FastAPI for all REST endpoints
```

---

## Step 4: Search Your Memory

```python
results = memory.search_decisions("What web framework are we using?")

for r in results:
    print(f"• {r['title']}")
    print(f"  Target:  {r['target']}")
    print(f"  Score:   {r['score']:.2f}")
    print(f"  Status:  {r['status']}")
```

Output:
```
• Use FastAPI for all REST endpoints
  Target:  web_framework
  Score:   0.93
  Status:  active
```

---

## Step 5: Update a Decision (Auto-Supersede)

The technology landscape evolves. Update your decision — LedgerMind handles the rest:

```python
memory.record_decision(
    title="Use FastAPI with Pydantic v2 and async SQLAlchemy",
    target="web_framework",
    rationale="Pydantic v2 delivers 5-10x faster validation. "
              "Async SQLAlchemy enables non-blocking database operations.",
)
# No ConflictError — auto-supersede triggered because similarity > 85%

print("✓ Decision updated automatically")
```

Search again and see the truth resolved:
```python
results = memory.search_decisions("web framework", mode="balanced")
print(results[0]["title"])
# → Use FastAPI with Pydantic v2 and async SQLAlchemy

print(results[0]["status"])
# → active
```

The old record is preserved in Git history with `status=superseded`.

---

## Step 6: Record Interactions (Feed the Reflection Engine)

```python
# Simulate an agent interaction that failed
bridge.record_interaction(
    prompt="Connect to PostgreSQL on port 5432",
    response="psycopg2.OperationalError: could not connect to server",
    success=False
)

# And one that succeeded
bridge.record_interaction(
    prompt="Run database migration",
    response="Migration applied: 003_add_users_table.sql",
    success=True
)

print("✓ Interactions recorded")
```

---

## Step 7: Trigger Reflection

```python
# In MCP mode this runs automatically every 4 hours.
# Run it manually here to see it in action.
proposal_ids = memory.run_reflection()

if proposal_ids:
    print(f"✓ Generated {len(proposal_ids)} decision streams")
    for pid in proposal_ids:
        print(f"  → {pid}")
```

The Reflection Engine analyzed the error, generated a hypothesis proposal, and saved it to the semantic store for review.

---

## Step 8: Review Emergent Decision Streams

```python
# Search for draft proposals
all_records = memory.search_decisions("", mode="audit")
proposals = [r for r in all_records if r["kind"] == "proposal"]

for p in proposals:
    print(f"Proposal: {p['title']} (confidence: unknown, see full record)")

# Accept a proposal (promote it to an active decision)
if proposals:
    result = memory.accept_proposal(proposals[0]["id"])
    print(f"✓ Accepted → {result.metadata.get('file_id')}")
```

---

## Step 9: Use Context Injection

This is the core loop for autonomous agents: inject memory into every LLM call.

```python
user_question = "How should I set up the database connection?"

# Get relevant context from memory
context = bridge.get_context_for_prompt(user_question, limit=3)

if context:
    print("Memory context found:")
    print(context[:200] + "...")  # Preview first 200 chars
else:
    print("No relevant memory found")

# In a real agent:
# prompt = f"{context}\n\nUser: {user_question}"
# response = your_llm(prompt)
```

---

## Step 10: Check Health and Stats

```python
health = bridge.check_health()
print(f"Git available:    {'✓' if health['git_available'] else '✗'}")
print(f"Storage writable: {'✓' if health['storage_writable'] else '✗'}")
print(f"Vector search:    {'✓' if health['vector_available'] else '✗'}")

stats = bridge.get_stats()
print(f"\nEpisodic events:  {stats['episodic_count']}")
print(f"Semantic records: {stats['semantic_count']}")
print(f"Vector embeddings:{stats['vector_count']}")
```

---

## Complete Example

```python
from ledgermind.core.api.bridge import IntegrationBridge

def run_demo():
    # Recommended: storage path one level above the project
    bridge = IntegrationBridge(memory_path="../.ledgermind")
    memory = bridge.memory

    # Record decisions
    memory.record_decision(
        title="Use PostgreSQL as primary database",
        target="database",
        rationale="PostgreSQL provides ACID guarantees and excellent JSON support."
    )
    memory.record_decision(
        title="Use Redis for caching and session storage",
        target="caching",
        rationale="Redis sub-millisecond latency is ideal for session and hot-path caching."
    )

    # Simulate agent activity
    bridge.record_interaction("How to query users?", "SELECT * FROM users WHERE active=true", success=True)
    bridge.record_interaction("Cache miss on user profile", "KeyError: user:42 not found in Redis", success=False)

    # Search
    print("\n--- Searching for database decisions ---")
    for r in memory.search_decisions("database configuration", mode="strict"):
        print(f"  {r['title']} [{r['status']}]")

    # Update a decision (auto-supersede)
    print("\n--- Updating database decision ---")
    memory.record_decision(
        title="Use Aurora PostgreSQL for auto-scaling",
        target="database",
        rationale="Aurora PostgreSQL provides serverless scaling with full PostgreSQL compatibility."
    )

    # Reflect
    print("\n--- Running reflection ---")
    streams = memory.run_reflection()
    print(f"  Generated or updated {len(streams)} streams")

    # Stats
    stats = bridge.get_stats()
    print(f"\n--- Stats ---")
    print(f"  Semantic: {stats['semantic_count']} records")
    print(f"  Episodic: {stats['episodic_count']} events")


if __name__ == "__main__":
    run_demo()
```

---

## Next Steps

- **[API Reference](../API_REFERENCE.md)** — Full documentation of every method
- **[Workflows](../WORKFLOWS.md)** — Detailed guides for common patterns
- **[Integration Guide](../INTEGRATION_GUIDE.md)** — Production deployment with MCP server
- **[Configuration](../CONFIGURATION.md)** — Tune LedgerMind for your use case
- **[Architecture](../ARCHITECTURE.md)** — Understand how it works internally
