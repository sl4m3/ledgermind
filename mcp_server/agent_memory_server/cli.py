import argparse
import os
import json
from agent_memory_server.server import MCPServer

def export_schemas():
    """Outputs the formal industrial-grade API specification."""
    from agent_memory_server.specification import MCPApiSpecification
    spec = MCPApiSpecification.generate_full_spec()
    print(json.dumps(spec, indent=2))

def init_project(path: str, role: str):
    """Initializes a new memory project structure and default config."""
    import yaml
    from agent_memory_core.api.memory import Memory
    
    print(f"Initializing Agent Memory project at {path}...")
    
    # Initialize directory structure and Git repo via Core API
    try:
        Memory(storage_path=path)
        print(f"✓ Created memory structure at {path}")
    except Exception as e:
        print(f"✗ Error initializing storage: {e}")
        return

    # Create default configuration file
    config = {
        "memory": {
            "path": path,
            "role": role,
            "name": "AgentMemory",
            "capabilities": None
        }
    }
    
    config_file = "memory_config.yaml"
    if os.path.exists(config_file):
        print(f"! {config_file} already exists, skipping config generation.")
    else:
        with open(config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        print(f"✓ Created default configuration in {config_file}")
    
    print("\nInitialization complete! You can now start the server with:")
    print(f"  agent-memory-mcp run --path {path}")

def main():
    parser = argparse.ArgumentParser(description="Agent Memory MCP Server Launcher")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command (default)
    run_parser = subparsers.add_parser("run", help="Run the MCP server")
    run_parser.add_argument("--path", default=".agent_memory", help="Path to memory storage")
    run_parser.add_argument("--name", default="AgentMemory", help="MCP Server Name")
    run_parser.add_argument("--role", default="agent", choices=["viewer", "agent", "admin"], help="Authority role")
    run_parser.add_argument("--capabilities", help="JSON string of capabilities (e.g. '{\"read\": true}')")
    run_parser.add_argument("--capability", action="store_true", help="Enable capability-based mode")
    run_parser.add_argument("--metrics-port", type=int, help="Port to expose Prometheus metrics")
    run_parser.add_argument("--webhooks", nargs="+", help="Space-separated list of webhook URLs")
    run_parser.add_argument("--rest-port", type=int, help="Port to run the REST API Gateway")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize a new memory project")
    init_parser.add_argument("--path", default=".agent_memory", help="Path to create memory storage")
    init_parser.add_argument("--role", default="agent", choices=["viewer", "agent", "admin"], help="Default role in config")

    # Export schema command
    subparsers.add_parser("export-schema", help="Export JSON schemas for API contracts")
    
    args = parser.parse_args()
    
    if args.command == "export-schema":
        export_schemas()
    elif args.command == "init":
        init_project(args.path, args.role)
    else:
        # Default to run if no command specified (for backward compatibility)
        path = getattr(args, "path", ".agent_memory")
        name = getattr(args, "name", "AgentMemory")
        role = getattr(args, "role", "agent")
        caps_str = getattr(args, "capabilities", None)
        is_capability_mode = getattr(args, "capability", False)
        
        capabilities = None
        if caps_str:
            try:
                capabilities = json.loads(caps_str)
            except json.JSONDecodeError:
                print(f"Error: Invalid JSON for capabilities: {caps_str}")
                return
        elif is_capability_mode:
            capabilities = {}

        MCPServer.serve(
            storage_path=path,
            server_name=name,
            role=role,
            capabilities=capabilities,
            metrics_port=getattr(args, "metrics_port", None),
            webhook_urls=getattr(args, "webhooks", None),
            rest_port=getattr(args, "rest_port", None)
        )

if __name__ == "__main__":
    main()
