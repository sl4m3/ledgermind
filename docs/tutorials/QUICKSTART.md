# Quickstart Tutorial: Building a Code Analysis Agent with Memory

This guide will walk you through creating a simple agent that uses the Ledgermind to track architectural decisions and code style rules.

## Prerequisites

```bash
pip install ledgermind
```

## Quick Start (Direct Library Access)

For local CLI tools or autonomous agents, use the `IntegrationBridge` for the simplest integration.

```python
from ledgermind.core.api.bridge import IntegrationBridge

# Initialize the memory system
bridge = IntegrationBridge(memory_path="./project_memory")
memory = bridge.memory
```

## 1. Record an Architectural Decision

Imagine your agent analyzes a codebase and decides that the project should use **FastAPI** for its speed.

```python
memory.record_decision(
    title="Use FastAPI for the Web Layer",
    target="web_framework",
    rationale="FastAPI provides high performance and automatic OpenAPI generation, which is essential for our microservices."
)
print("Decision recorded!")
```

## 3. Search for Knowledge

Later, the agent (or another agent) needs to know which framework to use.

```python
# Search using semantic query
results = memory.search_decisions("Which framework are we using for the web layer?")

for res in results:
    print(f"Found: {res['title']} (Status: {res['status']})")
    print(f"Rationale: {res['rationale']}")
```

## 4. Evolve Knowledge (Supersede)

Technology changes. A year later, the team decides to move to **Go (Gin)** for even better performance. Instead of deleting the old memory, we **supersede** it.

```python
# Get the ID of the old decision
old_decisions = memory.search_decisions("FastAPI", mode="audit")
old_id = old_decisions[0]['id']

# Create a new decision that replaces the old one
memory.supersede_decision(
    title="Migrate to Go (Gin) for Web Layer",
    target="web_framework",
    rationale="While FastAPI served us well, we need the concurrency model of Go to handle 10k+ requests per second.",
    old_decision_ids=[old_id]
)
print("Policy updated!")
```

## 5. Truth Resolution

If you search now, the system will prioritize the **Active** Go decision, even if you search for "FastAPI" (due to Recursive Truth Resolution).

```python
# Even if searching for 'FastAPI', the system knows it's superseded
results = memory.search_decisions("FastAPI web framework", mode="balanced")
print(f"Top result: {results[0]['title']} (Status: {results[0]['status']})")
# Output: Top result: Migrate to Go (Gin) for Web Layer (Status: active)
```

## 6. Audit Trail (Git)

Every operation above created a Git commit. You can check the history:

```bash
cd project_memory
git log --oneline
```

This ensures that every change in the agent's "mind" is fully auditable by humans.
