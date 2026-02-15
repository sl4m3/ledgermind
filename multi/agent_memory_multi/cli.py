import argparse
import os
from agent_memory_multi.adapters.mcp_adapter import MCPMemoryAdapter

def main():
    parser = argparse.ArgumentParser(description="Agent Memory MCP Server Launcher")
    parser.add_argument("--path", default=".agent_memory", help="Path to memory storage")
    parser.add_argument("--name", default="AgentMemory", help="MCP Server Name")
    
    args = parser.parse_args()
    
    # Запуск через наш новый упрощенный метод
    MCPMemoryAdapter.serve(
        storage_path=args.path,
        server_name=args.name
    )

if __name__ == "__main__":
    main()
