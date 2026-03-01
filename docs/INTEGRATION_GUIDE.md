# Integration Guide

LedgerMind supports two integration modes: **direct library embedding** and **MCP server**. This guide covers both patterns with production-ready examples.

---

## Choosing an Integration Mode

| Criterion | Client Hooks (Zero-Touch) | MCP Server | Library Mode |
|---|---|---|---|
| Deployment | Native hooks / Extension | Separate process | Embedded in your agent process |
| Agent compatibility | VS Code, Claude, Cursor, Gemini | Any MCP client | Python only |
| Agent Effort | **None** (Automatic) | Manual Tool Calls | Manual Code |
| Best for | Daily coding, Chat interfaces | Complex multi-agent setups | Fully autonomous Python agents |

---

## Zero-Touch Automation (Client Hooks)

The easiest and most powerful way to use LedgerMind is via the **LedgerMind Hooks Pack**. This feature injects lightweight scripts or extensions into your favorite LLM clients (VS Code, Cursor, Gemini CLI, Claude Code). 

Once installed, LedgerMind automatically:
1. Retrieves project context and rules *before* every prompt you send.
2. Records every interaction, tool execution, and agent thought *after* it happens.
3. Completely frees the LLM from spending tokens on manual MCP tool calls.

### Installation

Run the interactive installer from your project directory:

```bash
ledgermind init
```

During initialization, you will be asked to choose a client. LedgerMind will install the hooks **locally within your project directory** (e.g., in `.ledgermind/hooks/` or `.gemini/hooks/`) and update your client's global configuration to point to these local scripts. 

**Why Local?** This architecture ensures strict isolation. Your global client knows how to trigger hooks, but the hooks themselves are tied directly to the codebase and memory database of the specific project you are working in.

### How it Works Under the Hood

- **VS Code (Hardcore):** Installs a background extension that monitors file saves, terminal data, and chat interactions. It maintains a `ledgermind_context.md` "shadow file" for proactive context injection.
- **Claude/Cursor/Gemini:** Injects native client hooks (e.g., `UserPromptSubmit` in Claude, `beforeSubmitPrompt` in Cursor, or `ledgermind_hook.py` in Gemini). These scripts are saved inside your project folder.

These hooks call the lightweight **Bridge API** via CLI (`bridge-context` and `bridge-record`). This approach bypasses the need for a running MCP server and executes memory operations in milliseconds directly against the SQLite/Git stores.

### Autonomous Knowledge Enrichment (v3.1.0)

During setup (`ledgermind init`), you can configure the **Arbitration Mode** to enable background Knowledge Enrichment via the `LLMEnricher`.

- **Local LLMs (e.g., Ollama, Gemini CLI):** Ideal for privacy. LedgerMind will run the enrichment pipeline completely offline, querying your local CLI/server to translate raw technical clusters into human-readable insights.
- **Remote APIs:** For higher quality summarization, LedgerMind can use cloud APIs securely.
- **Lite Mode:** Bypasses LLM enrichment entirely for maximum performance on constrained devices.

Because enrichment runs asynchronously in the background maintenance worker, it **never adds latency** to your active coding or chat sessions.

---

## Library Integration

### Installation

```bash
pip install ledgermind
```

### Minimal Setup

```python
from ledgermind.core.api.bridge import IntegrationBridge

# Recommended: storage path one level above the project
bridge = IntegrationBridge(memory_path="../.ledgermind")
```

`IntegrationBridge` is the recommended entry point for most use cases. It wraps the `Memory` class with simplified methods and safe error handling.

### Full Autonomous Agent Pattern

```python
from ledgermind.core.api.bridge import IntegrationBridge

bridge = IntegrationBridge(
    memory_path="../.ledgermind",
    relevance_threshold=0.7,   # minimum relevance score for context injection
)

def agent_step(user_input: str) -> str:
    # 1. Retrieve relevant memory context
    context = bridge.get_context_for_prompt(user_input, limit=3)

    # 2. Build enriched prompt
    prompt = f"{context}\n\nUser: {user_input}" if context else f"User: {user_input}"

    # 3. Call your LLM
    response = your_llm(prompt)

    # 4. Record the interaction (feeds future reflection)
    bridge.record_interaction(user_input, response, success="error" not in response.lower())

    return response


def agent_learn(title: str, target: str, rationale: str):
    """Record a decision discovered during operation."""
    bridge.memory.record_decision(title=title, target=target, rationale=rationale)


def agent_maintenance():
    """Call periodically (e.g. every hour) if not using MCP mode."""
    report = bridge.run_maintenance()
    print(f"Maintenance: {report}")
```

### Direct Memory API

For full control, use the `Memory` class directly:

```python
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import LedgermindConfig, TrustBoundary

config = LedgermindConfig(
    storage_path="../.ledgermind",
    ttl_days=60,
    trust_boundary=TrustBoundary.AGENT_WITH_INTENT,
    namespace="my_agent_2.7.9",
)
memory = Memory(config=config)

# Record
memory.record_decision(
    title="Always validate input with Pydantic",
    target="input_validation",
    rationale="Pydantic 2.7.9 provides fast, type-safe validation with clear error messages."
)

# Search
results = memory.search_decisions("input validation approach", mode="strict")

# Audit history
history = memory.get_decision_history(results[0]["id"])

# Visualize
print(memory.generate_knowledge_graph(target="input_validation"))
```

### Pluggable Storage

You can inject custom storage backends:

```python
from ledgermind.core.api.memory import Memory
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.stores.semantic import SemanticStore
from ledgermind.core.stores.audit_no import NoAuditProvider  # Git-free

# Custom episodic store (e.g. in /tmp for testing)
episodic = EpisodicStore(db_path="/tmp/test_episodic.db")

# Semantic store without Git (useful in environments without Git)
audit = NoAuditProvider(repo_path="/tmp/test_semantic")
semantic = SemanticStore(repo_path="/tmp/test_semantic", audit_store=audit)

memory = Memory(
    storage_path="/tmp/test_memory",
    episodic_store=episodic,
    semantic_store=semantic,
)
```

---

## MCP Server Integration

### Starting the Server

```bash
# Basic
ledgermind-mcp run --path ../.ledgermind

# Production
ledgermind-mcp run \
      --path ../.ledgermind \  --name "ProjectMemory" \
  --metrics-port 9090 \
  --rest-port 8080
```

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or equivalent:

```json
{
  "mcpServers": {
    "ledgermind": {
      "command": "ledgermind-mcp",
      "args": ["run", "--path", "/absolute/path/to/memory"]
    }
  }
}
```

### Gemini CLI Configuration

```json
{
  "mcpServers": {
    "ledgermind": {
      "command": "ledgermind-mcp",
      "args": ["run", "--path", "../.ledgermind"]
    }
  }
}
```

### Programmatic MCP Server

```python
from ledgermind.server.server import MCPServer
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import TrustBoundary

memory = Memory(
    storage_path="../.ledgermind",
    trust_boundary=TrustBoundary.AGENT_WITH_INTENT
)

server = MCPServer(
    memory=memory,
    server_name="MyAgent Memory",
    storage_path="../.ledgermind",
    capabilities={
        "read": True,
        "propose": True,
        "supersede": True,
        "accept": True,
        "sync": True,
        "purge": False,  # Keep purge disabled for safety
    },
    metrics_port=9090,
    rest_port=8080,
)

server.run()
```

---

## REST API Integration

When started with `--rest-port`, LedgerMind exposes a FastAPI server:

```python
import httpx

base = "http://localhost:8080"

# Search
resp = httpx.post(f"{base}/search", json={"query": "database config", "limit": 5})
results = resp.json()["results"]

# Record
resp = httpx.post(f"{base}/record", json={
    "title": "Use connection pooling",
    "target": "database",
    "rationale": "Connection pooling reduces latency by reusing existing connections."
})
new_id = resp.json()["id"]
```

### Server-Sent Events (real-time updates)

```javascript
const source = new EventSource("http://localhost:8080/events");
source.addEventListener("decision_created", (e) => {
    console.log("New decision:", JSON.parse(e.data));
});
```

### WebSocket

```python
import websockets
import asyncio
import json

async def listen():
    async with websockets.connect("ws://localhost:8080/ws") as ws:
        async for message in ws:
            event = json.loads(message)
            print(f"Memory event: {event['event']} → {event['data']}")

asyncio.run(listen())
```

---

## Autonomous Behavior in MCP Mode

When using the MCP server, the `BackgroundWorker` handles all maintenance automatically. Here is what happens without any manual intervention:

```
Every 5 minutes:
  ├── Health check: detect and remove stale locks (> 10 min old)
  ├── Git sync: index last 5 commits as episodic events
  └── (sub-interval checks below)

Every 1 hour:
  └── Decay cycle:
      ├── Archive episodic events older than ttl_days
      ├── Reduce confidence of inactive semantic records
      └── Hard-delete records below forget_threshold

Every 4 hours:
  └── Reflection cycle:
      ├── Cluster episodic events by target
      ├── Detect behavioral patterns and temporal signals
      ├── Evaluate reinforcement density and stream stability
      └── Update phases and vitality (`PATTERN` -> `EMERGENT` -> `CANONICAL`)
```

### Recommendations for Production

1. **Trust auto-supersede.** When an agent updates its knowledge, just call `record_decision()` again. The system resolves the history automatically for incremental changes.

2. **Use Target Registry aliases.** Before deploying, register your domain-specific aliases:
   ```python
   memory.targets.register("database_config", aliases=["db", "DB", "database"])
   memory.targets.register("api_settings", aliases=["api", "API_CONFIG"])
   ```

3. **Monitor the `/health` endpoint** (available via `get_environment_health` MCP tool) in your alerting system.

4. **Set `purge=false`** in capabilities unless your agent explicitly needs to delete records. The decay engine handles cleanup automatically.

5. **Use `mode="audit"` only for introspection.** Production queries should use `strict` or `balanced` to avoid returning outdated records.
