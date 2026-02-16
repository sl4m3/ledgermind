import asyncio
import os
import yaml
from typing import Optional, Dict, Any, Union
from contextlib import asynccontextmanager

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from agent_memory_adapters.mcp_client import MCPMemoryProxy, SyncMCPMemoryProxy

class Memory:
    """
    High-level entry point for Agent Memory System.
    Simplifies connection to MCP memory servers.
    """
    
    @staticmethod
    @asynccontextmanager
    async def connect(
        path_or_url: str, 
        role: str = "agent", 
        capabilities: Optional[Dict[str, bool]] = None,
        name: str = "AgentMemory"
    ):
        """
        Connect to a memory system via MCP.
        
        Args:
            path_or_url: Path to local memory directory or an MCP server URL.
            role: The role to assume (viewer, agent, admin).
            capabilities: Granular permissions (overrides role).
            name: Human-readable name for the server.
        """
        # If it's a local path, we assume we need to start the agent-memory-mcp server
        if os.path.isdir(path_or_url) or not path_or_url.startswith(("http://", "https://", "ws://")):
            # Local stdio connection
            args = ["run", "--path", path_or_url, "--name", name]
            if capabilities:
                import json
                args.extend(["--capabilities", json.dumps(capabilities)])
            else:
                args.extend(["--role", role])
            
            server_params = StdioServerParameters(command="agent-memory-mcp", args=args)
            
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield MCPMemoryProxy(session)
        else:
            # Future: Support for SSE/WebSocket connections
            raise NotImplementedError("Remote URLs (SSE/WS) are not yet supported in this convenience wrapper.")

    @classmethod
    async def from_config(cls, config_path: str):
        """
        Initialize connection from a YAML configuration file.
        """
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        memory_config = config.get("memory", {})
        return cls.connect(
            path_or_url=memory_config.get("path", "./.agent_memory"),
            role=memory_config.get("role", "agent"),
            capabilities=memory_config.get("capabilities"),
            name=memory_config.get("name", "AgentMemory")
        )

class SyncMemory:
    """Synchronous version of the Memory connector."""
    
    @staticmethod
    def connect(path_or_url: str, **kwargs):
        """
        Synchronous connection to memory. 
        Returns a SyncMCPMemoryProxy that can be used directly with standard LLM adapters.
        Note: This internally manages an event loop.
        """
        import nest_asyncio
        nest_asyncio.apply()
        
        # This is a bit complex for a simple 'connect' because of the async context manager.
        # For simplicity in sync mode, we'll implement a dedicated sync connector or 
        # use a background thread for the MCP session.
        # For now, providing a warning or a simple blocking call.
        raise NotImplementedError("SyncMemory.connect is not yet fully implemented. Use 'async with Memory.connect(...)'.")
