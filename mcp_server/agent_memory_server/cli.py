import argparse
import os
import json
from agent_memory_server.server import MCPServer

def export_schemas():
    """Outputs the formal industrial-grade API specification."""
    from agent_memory_server.specification import MCPApiSpecification
    spec = MCPApiSpecification.generate_full_spec()
    print(json.dumps(spec, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Agent Memory MCP Server Launcher")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command (default)
    run_parser = subparsers.add_parser("run", help="Run the MCP server")
    run_parser.add_argument("--path", default=".agent_memory", help="Path to memory storage")
    run_parser.add_argument("--name", default="AgentMemory", help="MCP Server Name")
    run_parser.add_argument("--role", default="agent", choices=["viewer", "agent", "admin"], help="Authority role")
    run_parser.add_argument("--capabilities", help="JSON string of capabilities (e.g. '{\"read\": true}')")
    
    # Export schema command
    subparsers.add_parser("export-schema", help="Export JSON schemas for API contracts")
    
    args = parser.parse_args()
    
    if args.command == "export-schema":
        export_schemas()
    else:
        # Default to run if no command specified (for backward compatibility)
        path = getattr(args, "path", ".agent_memory")
        name = getattr(args, "name", "AgentMemory")
        role = getattr(args, "role", "agent")
        caps_str = getattr(args, "capabilities", None)
        
        capabilities = None
        if caps_str:
            try:
                capabilities = json.loads(caps_str)
            except json.JSONDecodeError:
                print(f"Error: Invalid JSON for capabilities: {caps_str}")
                return

        MCPServer.serve(
            storage_path=path,
            server_name=name,
            role=role,
            capabilities=capabilities
        )

if __name__ == "__main__":
    main()
