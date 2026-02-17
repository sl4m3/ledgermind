import argparse
import os
import json
from agent_memory_server.server import MCPServer

def export_schemas():
    """Outputs the formal industrial-grade API specification."""
    from agent_memory_server.specification import MCPApiSpecification
    spec = MCPApiSpecification.generate_full_spec()
    print(json.dumps(spec, indent=2))

def init_project(path: str):
    """Initializes a new memory project structure."""
    from agent_memory_core.api.memory import Memory
    
    print(f"Initializing Agent Memory project at {path}...")
    
    # Initialize directory structure and Git repo via Core API
    try:
        Memory(storage_path=path)
        print(f"✓ Created memory structure at {path}")
    except Exception as e:
        print(f"✗ Error initializing storage: {e}")
        return

    print("\nInitialization complete! You can now start the server with:")
    print(f"  agent-memory-mcp run --path {path}")

def main():
    parser = argparse.ArgumentParser(description="Agent Memory MCP Server Launcher")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run the MCP server")
    run_parser.add_argument("--path", default=".agent_memory", help="Path to memory storage")
    run_parser.add_argument("--name", default="AgentMemory", help="MCP Server Name")
    run_parser.add_argument("--capabilities", help="JSON string of capabilities")
    run_parser.add_argument("--metrics-port", type=int, help="Port for Prometheus metrics")
    run_parser.add_argument("--rest-port", type=int, help="Port for REST Gateway")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize a new memory project")
    init_parser.add_argument("--path", default=".agent_memory", help="Path to create memory storage")

    # Export schema command
    subparsers.add_parser("export-schema", help="Export JSON schemas for API contracts")
    
    # Default to 'run' if no command is provided, but we need to handle arguments
    # A simple way is to check sys.argv
    import sys
    if len(sys.argv) > 1 and sys.argv[1] not in ["run", "init", "export-schema", "-h", "--help"]:
        # Insert 'run' as the default command
        sys.argv.insert(1, "run")

    args = parser.parse_args()
    
    if args.command == "export-schema":
        export_schemas()
    elif args.command == "init":
        init_project(args.path)
    elif args.command == "run":
        capabilities = None
        if args.capabilities:
            try:
                capabilities = json.loads(args.capabilities)
            except json.JSONDecodeError:
                print(f"Error: Invalid JSON for capabilities: {args.capabilities}")
                return

        MCPServer.serve(
            storage_path=args.path,
            server_name=args.name,
            capabilities=capabilities,
            metrics_port=args.metrics_port,
            rest_port=args.rest_port
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
