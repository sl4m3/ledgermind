import json
import asyncio
from typing import Any, Dict, List, Optional
from mcp import ClientSession

class MCPMemoryProxy:
    """
    Client-side proxy that implements the memory tool interface
    by forwarding calls to a remote MCP server via a ClientSession.
    """
    def __init__(self, session: ClientSession):
        self.session = session

    async def record_decision(self, **kwargs) -> Dict[str, Any]:
        return await self._call_tool("record_decision", kwargs)

    async def supersede_decision(self, **kwargs) -> Dict[str, Any]:
        return await self._call_tool("supersede_decision", kwargs)

    async def search_decisions(self, **kwargs) -> List[Dict[str, Any]]:
        resp = await self._call_tool("search_decisions", kwargs)
        return resp.get("results", [])

    async def accept_proposal(self, **kwargs) -> Dict[str, Any]:
        return await self._call_tool("accept_proposal", kwargs)

    async def sync_git_history(self, **kwargs) -> Dict[str, Any]:
        return await self._call_tool("sync_git_history", kwargs)

    async def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Helper to invoke a tool via the MCP session and parse the response."""
        result = await self.session.call_tool(name, arguments)
        if not result.content or len(result.content) == 0:
            return {"status": "error", "message": "No response from MCP server"}
            
        try:
            # MCP tools return text content which we expect to be JSON (based on our server implementation)
            text_resp = result.content[0].text
            return json.loads(text_resp)
        except (json.JSONDecodeError, AttributeError):
            return {"status": "error", "message": "Invalid JSON response from MCP server", "raw": result.content[0].text}

class SyncMCPMemoryProxy:
    """Synchronous wrapper for MCPMemoryProxy to maintain compatibility with legacy adapters."""
    def __init__(self, async_proxy: MCPMemoryProxy, loop: Optional[asyncio.AbstractEventLoop] = None):
        self.proxy = async_proxy
        self.loop = loop or asyncio.get_event_loop()

    def record_decision(self, **kwargs):
        return self._run(self.proxy.record_decision(**kwargs))

    def supersede_decision(self, **kwargs):
        return self._run(self.proxy.supersede_decision(**kwargs))

    def search_decisions(self, **kwargs):
        return self._run(self.proxy.search_decisions(**kwargs))

    def _run(self, coro):
        if self.loop.is_running():
            # If we are already in an async loop, this is tricky. 
            # In real usage, adapters should probably be async.
            import nest_asyncio
            nest_asyncio.apply()
        return self.loop.run_until_complete(coro)
