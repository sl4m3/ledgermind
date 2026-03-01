# Integration Guide

Complete guide to integrating LedgerMind with various clients and platforms.

---

## Introduction

This document covers all aspects of LedgerMind integration for:

- **DevOps Engineers** deploying MCP servers
- **Developers** building custom LLM integrations or extending functionality
- **Tool Authors** implementing custom MCP tools
- **System Administrators** configuring multi-agent deployments

**Integration Approaches Overview**:

| Approach | Complexity | Control | Best For | Use Cases |
|-----------|-----------|---------|-----------|------------|
| **MCP Server** | Medium | High | Production deployments | FastMCP server, multiple clients |
| **IntegrationBridge** | Low | Low | Single-process applications, CLI tools | Local LLMs, custom flow control |
| **VS Code Extension** | High | Medium | VS Code native features | Hardcore mode, shadow injection |

---

## Integration Approaches

### MCP Server Integration

Use LedgerMind as a Model Context Protocol (MCP) server for any MCP-compatible client (Claude, Cursor, etc.).

**Setup**:

```bash
# 1. Start LedgerMind MCP server
ledgermind run --path ~/.ledgermind --metrics-port 9090

# 2. Configure your client's MCP settings
# In Claude Desktop:
# - Open Claude Desktop Settings
# - Add new MCP server: "mcp://localhost:9090"
# - Enable the server

# In Cursor IDE:
# - Open Cursor Settings
# - Add MCP server configuration
# - Restart Cursor

# 3. Verify connection
# Try using a tool (e.g., search_decisions)
```

**Advantages**:
- Full access to all 15 MCP tools
- No need for custom code or adapters
- Server manages all state internally
- Automatic authentication and authorization

**Configuration Options**:
```bash
# Role-based access
ledgermind run --path ~/.ledgermind --default-role ADMIN

# Custom capabilities
ledgermind run --path ~/.ledgermind --capabilities '{"sync":false,"reflect":false}'

# Webhooks (async event notifications)
ledgermind run --path ~/.ledgermind --capabilities '{"webhooks":["https://my-server.com/hook"]}'

# Metrics endpoint
ledgermind run --path ~/.ledgermind --metrics-port 9091
```

**Tool Usage**:

```python
# Example: Record a decision
result = client.call_tool("record_decision", {
    "title": "Use PostgreSQL for production",
    "target": "database",
    "rationale": "ACID compliance and proven reliability",
    "namespace": "production"
})

# Example: Search decisions
result = client.call_tool("search_decisions", {
    "query": "database schema",
    "limit": 5,
    "mode": "balanced"
})
```

**Authentication**:

If `LEDGERMIND_API_KEY` is set, clients must provide it via headers:

```bash
# Set API key
export LEDGERMIND_API_KEY="your-secure-random-key"

# Or pass via client configuration
# In Claude Desktop MCP configuration:
{
  "env": {
    "LEDGERMIND_API_KEY": "your-key"
  }
}
```

---

### IntegrationBridge API

For direct Python library integration without running an MCP server.

**When to Use**:
- **Single-process applications** (CLI tools, scripts, automated workflows)
- **Local LLM integration** (Ollama, DeepSeek, custom LLMs)
- **Custom flow control** beyond MCP server's capabilities

**When NOT to Use**:
- **MCP-compatible IDEs** (Claude Desktop, Cursor, etc.) — Use MCP server integration instead
- **Multi-client environments** — Each client runs its own MCP server

**Advantages**:
- Direct Python API access
- No network overhead
- Easier testing and debugging
- Can run in background threads
- Full control over memory lifecycle

**Basic Usage**:

```python
from ledgermind.core.api.bridge import IntegrationBridge

# Initialize
bridge = IntegrationBridge(
    memory_path="../.ledgermind",
    relevance_threshold=0.7,  # Only return 70%+ relevant results
    vector_model="../.ledgermind/models/3.1.2-small-text-matching-Q4_K_M.gguf",
    retention_turns=10,          # Remember context for N conversation turns
    default_cli=["gemini"],   # Use Gemini as default arbitrator
    memory_instance=None           # Optional: reuse existing Memory instance
)

# Get context for a prompt
context = bridge.get_context_for_prompt(
    "How should I handle database migrations?",
    limit=3
)

# Record a decision
bridge.record_decision(
    title="Use exponential backoff",
    target="api_client",
    rationale="Prevents overwhelming server during outages. "
             "Start with 1s delay, double up to 10s max.",
    consequences=[
        "Implement jitter",
        "Circuit breaker pattern"
    ]
)

# Record an interaction
bridge.record_interaction(
    prompt="Test API endpoint",
    response="200 OK",
    success=True,
    metadata={
        "tool_used": "http_client",
        "duration_seconds": 1.2
    }
)
```

**Initialization Options**:

| Parameter | Type | Default | Description |
|-----------|------|----------|-------------|
| `memory_path` | str | `"../.ledgermind"` | Path to memory storage |
| `relevance_threshold` | float | `0.7` | Minimum relevance for context (0.0-1.0) |
| `retention_turns` | int | `10` | How many turns to remember context |
| `vector_model` | str | Default model path | Path to GGUF model |
| `default_cli` | List[str] | `["gemini"]` | Default LLMs for arbitration |
| `memory_instance` | Memory | `None` | Optional: reuse existing Memory instance |

**Context Retrieval**:

```python
def get_context_for_prompt(
    self,
    prompt: str,
    limit: int = 3
) -> str:
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|----------|-------------|
| `prompt` | str | — | User's prompt to get context for |
| `limit` | int | `3` | Maximum number of memories to retrieve |

**Output Format**:

Returns formatted JSON string with prefix:

```json
{
  "source": "ledgermind",
  "memories": [
    {
      "id": "decision_id",
      "title": "Decision Title",
      "target": "target",
      "score": 0.85,
      "status": "active",
      "kind": "decision",
      "path": "/absolute/path/to/decision_id.md",
      "content": "Decision content...",
      "rationale": "Why this decision was made...",
      "instruction": "Key fields are injected. Use 'cat /path/to/file.md' if you need full history.",
      "procedural_guide": [
        "1. Step one",
        "2. Step two"
      ]
    }
  ]
}
```

**Integration Point**: The JSON output is designed to be directly injected into your LLM client's prompt as additional context.

---

### Customizing Behavior

#### Custom Arbitrater

```python
from ledgermind.core.api.bridge import IntegrationBridge

def my_arbiter(new_decision: Dict, old_decisions: List[Dict]) -> str:
    """
    Custom conflict resolution function.
    Returns: "supersede" to accept new decision.
    """
    # Your custom LLM logic here
    decision = call_llm(new_decision, old_decisions)
    # Analyze conflicts and determine action
    if decision == "supersede":
        return "supersede"
    return "deprecate"  # Mark old as outdated

bridge = IntegrationBridge(arbiter_callback=my_arbiter)
```

**Usage**:

```python
# With custom arbiter
bridge.record_decision(
    title="Use MongoDB",
    target="database",
    rationale="MongoDB provides flexibility and horizontal scaling.",
    arbiter_callback=my_arbiter
)
```

#### Custom Memory Instance

```python
from ledgermind.core.api.memory import Memory

# Create custom memory instance
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.stores.semantic import SemanticStore

custom_memory = Memory(
    episodic_store=EpisodicStore("/custom/episodic.db"),
    semantic_store=SemanticStore(
        repo_path="/custom/semantic",
        trust_boundary=TrustBoundary.AGENT_WITH_INTENT
    )
)

# Use with IntegrationBridge
from ledgermind.core.api.bridge import IntegrationBridge

bridge = IntegrationBridge(
    memory_instance=custom_memory,
    custom_flows=True
)
```

**Benefits**:
- Pre-configured storage backends
- Custom trust boundaries
- Shared state across multiple integrations

---

## VS Code Extension Integration

### Installation

**Via VS Code Marketplace**:

```bash
# Search for "ledgermind" in Extensions
code --install-extension ledgermind-vscode

# Or build from source
git clone https://github.com/sl4m3/ledgermind-vscode
cd ledgermind-vscode
npm install
```

**Features**:

| Feature | Description | Configuration |
|--------|-------------|----------|-------------|
| **Shadow Context Injection** | Automatically injects relevant memory into prompts | `hardcoreMode: true` | Injects without user prompt |
| **Terminal Monitoring** | Captures terminal output for evidence | `terminalMonitoring: true` |
| **Chat Participant** | Integrates with VS Code AI chat | Enables MCP tools in chat |
| **Namespace Configuration** | `namespace: "backend"` | Partition memory for backend operations |
| **Relevance Threshold** | `relevanceThreshold: 0.6` | Minimum 70% relevance |
| **Custom Hooks** | Optional: Override default injection behavior | `customHooks` object |

### Configuration Options

**Extension Settings** (`settings.json`):

```json
{
  "memoryPath": "/absolute/path/to/.ledgermind",
  "namespace": "default",
  "hardcoreMode": false,
  "terminalMonitoring": false,
  "chatParticipant": false,
  "relevanceThreshold": 0.7,
  "customHooks": {
    "beforePrompt": "custom_context_injection",
    "afterTool": "custom_post_processing"
  }
}
```

**Hardcore Mode**:

When enabled (`hardcoreMode: true`):
- **Behavior**: Automatically injects context WITHOUT showing it in UI
- **Use Case**: Background operations, automated tasks
- **Configuration**: Set via extension settings or file: `vscode/settings.json`

```json
{
  "hardcoreMode": true
}
```

**Terminal Monitoring**:

**Configuration**:

```json
{
  "terminalMonitoring": true,
  "terminalCapture": {
    "enabled": true,
    "captureOnCommand": true,
    "captureOnOutput": true,
    "includeErrors": true,
    "excludePatterns": ["password", "api.*key"]
  }
}
```

**Captured Content**:

Terminal commands, their output, and errors are automatically recorded as evidence.

---

## Language Client Integrations

### Claude Desktop CLI

**Approach**: Use Claude Desktop's MCP client.

**Setup**:

1. **Configure LedgerMind**:
   ```bash
   # Create config file for Claude Desktop MCP server
   echo '{"mcpServers": [
     {
       "command": "ledgermind run",
       "args": ["--path", "/absolute/path/to/.ledgermind"]
     }
   ]}' > ~/.claude/config.json
   ```

2. **Start Claude Desktop with config**:
   ```bash
   # Claude Desktop will load config and run LedgerMind
   ```

**Usage**:

```python
# Claude Desktop will automatically call LedgerMind MCP tools
# No additional code needed
```

### Cursor IDE

**Approach**: Use Cursor's MCP client.

**Setup**:

1. **Install hooks**:
   ```bash
   ledgermind install cursor --path /path/to/project
   ```

2. **Configure MCP server**:
   - Open Cursor Settings → Add MCP server
   - Restart Cursor to apply changes

**Hook Behavior**:

| Hook | Timing | Behavior |
|------|----------|----------|
| `beforeSubmitPrompt` | Before user sends prompt | Calls `bridge-context` |
| `afterAgentResponse` | After AI responds | Calls `bridge-record` (background) |
| `afterAgentThought` | After AI thinks | Calls `bridge-record` (background) |

**Integration Commands**:

```bash
# Manual install (if needed)
ledgermind install cursor --path /path/to/project

# Uninstall
ledgermind uninstall cursor --path /path/to/project
```

### Gemini CLI

**Approach**: Use Gemini CLI with hooks.

**Setup**:

```bash
ledgermind install gemini --path /path/to/project
```

**Hook File**: `.gemini/hooks/ledgermind_hook.py`

**Behavior**:

| Hook | Input | Output |
|------|----------|----------|
| `BeforeAgent` | JSON payload via stdin | Calls `bridge-context`, returns JSON with context |
| `AfterAgent` | JSON payload via stdin | Calls `bridge-record`, records interaction |

---

## Common Integration Patterns

### Authentication

**API Key**:

```bash
# Set API key for MCP server
export LEDGERMIND_API_KEY="your-secure-random-key"
```

**Client Configuration**:

```json
{
  "env": {
    "LEDGERMIND_API_KEY": "your-key"
  }
}
```

**Multi-Key Strategy**:

Use different API keys for:
- **Development environment** → Use one key per developer
- **Production vs Development** → Separate keys with different scopes

---

### Error Handling

**Common Error Codes**:

| Code | Message | Resolution |
|------|----------|----------|----------|
| `403 Forbidden` | Missing or invalid API key | Regenerate key or contact admin |
| `409 Conflict` | Decision conflict detected | Use `supersede_decision` with conflict list |
| `422 Unprocessable Entity | Validation error | Check request format and constraints |
| `429 Too Many Requests` | Rate limit exceeded | Wait before next request |

**Retry Strategies**:

```python
# Exponential backoff
import time
import random

retry_count = 0
max_retries = 5
base_delay = 1

while retry_count < max_retries:
    try:
        # Your operation here
        break
    except Exception as e:
        retry_count += 1
        delay = base_delay * (2 ** retry_count)
        time.sleep(delay + random.uniform(0, 1))
```

**Example**:

```python
def robust_search(query: str, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            results = bridge.search_decisions(query)
            return results
        except TemporaryFailure:
            continue
    raise MaxRetriesExceeded("Max retries exceeded")
```

---

### Context Filtering

**Namespace-Based Filtering**:

```python
# Search within specific namespace
results = bridge.search_decisions(
    "database migrations",
    namespace="production"
)
```

**Mode-Based Filtering**:

```python
# Get only active decisions (no history)
results = bridge.search_decisions(
    "database",
    mode="strict"
)
```

---

## Troubleshooting

### Connection Issues

**Problem**: Unable to connect to MCP server.

**Symptoms**:
- Timeout waiting for response
- Connection refused
- "Connection refused" error

**Solutions**:

```bash
# 1. Verify server is running
ps aux | grep ledgermind

# 2. Check configuration
# Verify CLI flags and port numbers

# 3. Check network connectivity
curl -I http://localhost:9090

# 4. Check API key
echo $LEDGERMIND_API_KEY

# 5. Restart client
# Restart your IDE or MCP client

# 6. Check logs
tail ~/.ledgermind/audit.log
```

### Authentication Failures

**Problem**: `403 Forbidden` - Missing or invalid API key.

**Solutions**:

```bash
# 1. Verify API key is set
echo $LEDGERMIND_API_KEY

# 2. Generate new key
python3 -c "import secrets; print(secrets.token_hex(32))"

# 3. Update configuration
# In Claude Desktop: Update env variable in settings.json
# In MCP client: Provide via --api-key flag or client config

# 4. Contact administrator
# If using shared server, contact server admin for new key
```

---

## Best Practices

### Security

**1. API Key Management**
- Use environment variables for local development
- Use different keys for production vs development
- Rotate API keys periodically
- Never commit API keys to version control
- Use least privilege principle (only grant needed capabilities)

**2. Data Isolation**
- Use namespaces to isolate different projects or agents
- Configure trust boundaries appropriately
- Separate development and production memories

**3. Error Handling**
- Implement retry logic with exponential backoff
- Validate all responses before acting on them
- Log all errors for debugging
- Never expose sensitive information in error messages

### Performance Optimization

**1. Context Injection**
- Use appropriate relevance thresholds for your use case
- Lower threshold for precision-critical tasks, higher for discovery
- Limit context size to avoid overwhelming prompts

**2. Batch Operations**
- Use `search_decisions()` with appropriate limit for bulk reads
- Leverage evidence linking for batch updates

**3. Caching**
- Enable vector store embedding cache
- Use IntegrationBridge retention turns to avoid repeated queries

**4. Connection Management**
- Keep connections alive and reuse when possible
- Use connection pooling for high-throughput operations
- Monitor connection health and implement circuit breakers

---

## Next Steps

For implementation details:
- [Quick Start](quickstart.md) — Step-by-step setup
- [Configuration](configuration.md) — Environment variables and options
- [API Reference](api-reference.md) — Method signatures
- [Data Schemas](data-schemas.md) — Model definitions
- [Architecture](architecture.md) — System internals
- [Workflows](workflow.md) — Common operational patterns

For MCP tool details:
- [MCP Tools](mcp-tools.md) — Detailed documentation of all 15 tools

For troubleshooting:
- [Common Issues](#common-integration-issues) — See above section

---

