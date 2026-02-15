import argparse
import os
from agent_memory_server.server import MCPServer

def main():
    parser = argparse.ArgumentParser(description="Agent Memory MCP Server Launcher")
    parser.add_argument("--path", default=".agent_memory", help="Path to memory storage")
    parser.add_argument("--name", default="AgentMemory", help="MCP Server Name")
    parser.add_argument("--role", default="agent", choices=["viewer", "agent", "admin"], help="Authority role for this session")
    
    args = parser.parse_args()
    
    MCPServer.serve(
        storage_path=args.path,
        server_name=args.name,
        role=args.role
    )

if __name__ == "__main__":
    main()
