# Ledgermind Integration Guide

Ledgermind is designed to be embedded directly into AI agents or accessed via the Model Context Protocol (MCP). This guide covers both approaches.

## 1. Direct Embedding (Library Mode)

This is the recommended approach for building autonomous agents where Ledgermind acts as the "Brain Core".

### Installation
```bash
pip install ledgermind
```

### Basic Usage with IntegrationBridge
The `IntegrationBridge` provides a high-level API for the most common tasks.

```python
from ledgermind.core.api.bridge import IntegrationBridge

# 1. Initialize the bridge
bridge = IntegrationBridge(memory_path="./my_agent_memory")

# 2. Check health (recommended for production)
health = bridge.check_health()
if health["errors"]:
    print(f"Memory system issues: {health['errors']}")

# 3. Inject context into your prompt
user_query = "How do I configure the database?"
context = bridge.get_context_for_prompt(user_query)

full_prompt = f"{context}

User: {user_query}"
# Send full_prompt to your LLM...

# 4. Record the interaction
agent_response = "You should use the config.yaml file..."
bridge.record_interaction(user_query, agent_response)

# 5. Periodic maintenance (run this occasionally)
bridge.run_maintenance()
```

## 2. Integration via MCP (Modular Mode)

Use this approach if you want to keep memory as a separate process or use multiple different tools to access the same memory.

### Start the Server
```bash
ledgermind-mcp run --path ./.memory
```

Any MCP-compatible client (like Gemini CLI, Claude Desktop, or custom scripts using `mcp` library) can connect to this server and use the provided tools: `search_decisions`, `record_decision`, `supersede_decision`, etc.

## 3. Best Practices for Production

1.  **Namespace your memory**: Use different storage paths for different agents or projects.
2.  **Regular Maintenance**: Call `bridge.run_maintenance()` or `bridge.trigger_reflection()` periodically (e.g., once a day or after 100 interactions) to distill episodic events into permanent semantic knowledge.
3.  **Handle Git Locks**: If you have multiple processes accessing the same memory, Ledgermind handles locks internally, but expect occasional slight delays in commit operations.
4.  **Vector Search**: For best performance in searching, ensure `sentence-transformers` is installed. Without it, Ledgermind falls back to keyword-based metadata search.
