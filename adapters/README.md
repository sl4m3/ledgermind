# Agent Memory Adapters (v2.0.0)

LLM-specific adapters for the Agent Memory System.
 These adapters connect to the Agent Memory Server exclusively via the Model Context Protocol (MCP), ensuring a clean separation between LLM logic and memory storage.

## Key Features
- **Protocol-Driven Architecture**: Implements strict `MemoryProvider` protocol for reliable interactions.
- **Decoupled Design**: No direct dependency on the `core` library implementation details.
- **Universal Interface**: Supports OpenAI, Anthropic, Gemini, and more via a unified contract.
- **Full Feature Support**: Includes `record_decision`, `supersede_decision`, `search_decisions`, `accept_proposal`, and `sync_git`.

## Usage Example (via MCP)
```python
from agent_memory_adapters.mcp_client import MCPMemoryProxy
from agent_memory_adapters.openai import OpenAIAdapter
from mcp import ClientSession
# ... setup your MCP transport (stdio/sse) ...

async def setup_agent(session: ClientSession):
    # Wrap MCP session into a Memory Proxy
    memory_proxy = MCPMemoryProxy(session)
    
    # Initialize adapter with the proxy (implements MemoryProvider)
    adapter = OpenAIAdapter(memory_provider=memory_proxy)
    
    # Get tool definitions for the LLM
    tools = adapter.get_tool_definitions()
    return tools
```

## Supported Frameworks & Providers
- **Direct Providers**: OpenAI, Anthropic, Google Gemini, Ollama.
- **Framework Integrations**: LangChain, CrewAI.
