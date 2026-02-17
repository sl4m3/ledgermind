# Agent Memory Adapters (v2.4.3)

LLM-specific adapters for the Agent Memory System. These adapters connect to the Agent Memory Server exclusively via the Model Context Protocol (MCP), ensuring a clean separation between LLM logic and memory storage.

## Key Features
- **Protocol-Driven Architecture**: Implements strict `MemoryProvider` protocol for reliable interactions.
- **Dynamic Semantic Search**: Full support for Google Gemini (text-embedding-004), OpenAI, and Ollama embeddings.
- **Decoupled Design**: No direct dependency on the `core` library implementation details.
- **Universal Interface**: Supports multiple LLM frameworks via a unified contract.

## Supported Frameworks & Providers
- **Direct Providers**: 
    - **Google Gemini** (via `google-generativeai`)
    - **OpenAI** (v1.0.0+)
    - **Anthropic** (Claude 3/3.5)
    - **Ollama** (Local Embeddings)
- **Framework Integrations**: 
    - **LangChain** (Tool calling and Memory)
    - **CrewAI** (Agent multi-memory support)

## Usage Example (via MCP)
```python
from agent_memory_adapters.mcp_client import MCPMemoryProxy
from agent_memory_adapters.google import GeminiAdapter
from mcp import ClientSession

async def setup_agent(session: ClientSession):
    # Wrap MCP session into a Memory Proxy
    memory_proxy = MCPMemoryProxy(session)
    
    # Initialize adapter with the proxy (implements MemoryProvider)
    adapter = GeminiAdapter(memory_provider=memory_proxy)
    
    # Get tools for the agent
    tools = adapter.get_tool_definitions()
    return tools
```

## Installation
```bash
pip install -e ./adapters
```
