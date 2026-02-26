import argparse
import os
import json
import logging
from typing import Optional
from ledgermind.server.server import MCPServer
from ledgermind.core.utils.logging import setup_logging

def export_schemas():
    """Outputs the formal industrial-grade API specification."""
    from ledgermind.server.specification import MCPApiSpecification
    spec = MCPApiSpecification.generate_full_spec()
    print(json.dumps(spec, indent=2))

def init_project(path: str):
    """Initializes a new memory project structure."""
    from ledgermind.core.api.memory import Memory
    
    print(f"Initializing Ledgermind project at {path}...")
    
    # Initialize directory structure and Git repo via Core API
    try:
        Memory(storage_path=path)
        print(f"✓ Created memory structure at {path}")
    except Exception as e:
        print(f"✗ Error initializing storage: {e}")
        return

    print("\nInitialization complete! You can now start the server with:")
    print(f"  ledgermind-mcp run --path {path}")

def check_project(path: str):
    """Runs diagnostics on an existing project."""
    from ledgermind.core.api.bridge import IntegrationBridge
    print(f"Running diagnostics for project at {path}...")
    try:
        bridge = IntegrationBridge(memory_path=path)
        health = bridge.check_health()
        
        print(f"Git Available: {'✓' if health['git_available'] else '✗'}")
        print(f"Storage Writable: {'✓' if health['storage_writable'] else '✗'}")
        print(f"Repo Healthy: {'✓' if health['repo_healthy'] else '✗'}")
        print(f"Vector Search: {'✓' if health['vector_available'] else '(!) Disabled'}")
        
        if health["errors"]:
            print("\nErrors Found:")
            for err in health["errors"]:
                print(f"  - {err}")
        
        if health["warnings"]:
            print("\nWarnings:")
            for warn in health["warnings"]:
                print(f"  - {warn}")
                
        if not health["errors"]:
             print("\n✓ Environment is healthy.")
    except Exception as e:
        print(f"✗ Fatal error during check: {e}")

def show_stats(path: str):
    """Displays memory statistics."""
    from ledgermind.core.api.bridge import IntegrationBridge
    try:
        bridge = IntegrationBridge(memory_path=path)
        stats = bridge.get_stats()
        print(f"Memory Statistics for {path}:")
        print(f"  Episodic Events: {stats['episodic_count']}")
        print(f"  Semantic Decisions: {stats['semantic_count']}")
        print(f"  Vector Embeddings: {stats['vector_count']}")
    except Exception as e:
        print(f"✗ Error fetching stats: {e}")

def bridge_context(path: str, prompt: str, cli: Optional[str] = None, threshold: Optional[float] = None):
    """Bridge API: Returns context for a prompt without starting MCP server."""
    from ledgermind.core.api.bridge import IntegrationBridge
    import sys
    try:
        default_cli = [cli] if cli else None
        bridge = IntegrationBridge(memory_path=path, default_cli=default_cli, relevance_threshold=threshold if threshold is not None else 0.7)
        ctx = bridge.get_context_for_prompt(prompt)
        sys.stdout.write(ctx)
    except Exception as e:
        sys.stderr.write(f"✗ Error fetching context: {e}\n")

def bridge_record(path: str, prompt: str, response: str, success: bool, metadata: str, cli: Optional[str] = None):
    """Bridge API: Records interaction into episodic memory."""
    from ledgermind.core.api.bridge import IntegrationBridge
    import json
    try:
        default_cli = [cli] if cli else None
        bridge = IntegrationBridge(memory_path=path, default_cli=default_cli)
        meta = json.loads(metadata) if metadata else None
        bridge.record_interaction(prompt=prompt, response=response, success=success, metadata=meta)
    except Exception as e:
        print(f"✗ Error recording interaction: {e}")

def main():
    parser = argparse.ArgumentParser(description="Ledgermind MCP Server Launcher")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run the MCP server")
    run_parser.add_argument("--path", default="ledgermind", help="Path to memory storage")
    run_parser.add_argument("--name", default="Ledgermind", help="MCP Server Name")
    run_parser.add_argument("--capabilities", help="JSON string of capabilities")
    run_parser.add_argument("--metrics-port", type=int, help="Port for Prometheus metrics")
    run_parser.add_argument("--rest-port", type=int, help="Port for REST Gateway")
    run_parser.add_argument("--vector-workers", type=int, default=0, help="Number of workers for multi-process encoding (0=auto)")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize a new memory project")
    init_parser.add_argument("--path", default="ledgermind", help="Path to create memory storage")

    # Check command
    check_parser = subparsers.add_parser("check", help="Check project health")
    check_parser.add_argument("--path", default="ledgermind", help="Path to memory storage")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show project statistics")
    stats_parser.add_argument("--path", default="ledgermind", help="Path to memory storage")

    # Global options
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--log-file", help="Path to log file")

    # Export schema command
    subparsers.add_parser("export-schema", help="Export JSON schemas for API contracts")
    
    # Install hooks command
    install_parser = subparsers.add_parser("install", help="Install LedgerMind hooks into a client")
    install_parser.add_argument("client", choices=["claude", "cursor", "gemini"], help="Target client to install hooks for")
    install_parser.add_argument("--path", default=os.getcwd(), help="Current project path to bind hooks to")

    # Bridge commands
    bc_parser = subparsers.add_parser("bridge-context", help="Internal: get context")
    bc_parser.add_argument("--path", default="ledgermind", help="Path to memory storage")
    bc_parser.add_argument("--prompt", required=True, help="User prompt")
    bc_parser.add_argument("--cli", help="Default CLI for arbitration")
    bc_parser.add_argument("--threshold", type=float, help="Relevance threshold")

    br_parser = subparsers.add_parser("bridge-record", help="Internal: record interaction")
    br_parser.add_argument("--path", default="ledgermind", help="Path to memory storage")
    br_parser.add_argument("--prompt", required=True, help="User prompt")
    br_parser.add_argument("--response", required=True, help="Agent response")
    br_parser.add_argument("--success", action="store_true", default=True, help="Was successful")
    br_parser.add_argument("--metadata", default=None, help="JSON metadata")
    br_parser.add_argument("--cli", help="Default CLI for arbitration")

    # Default to 'run' if no command is provided, but we need to handle arguments
    # A simple way is to check sys.argv
    import sys
    known_commands = ["run", "init", "check", "stats", "export-schema", "install", "bridge-context", "bridge-record", "-h", "--help", "--verbose", "-v", "--log-file"]
    if len(sys.argv) > 1 and sys.argv[1] not in known_commands:
        # Insert 'run' as the default command
        sys.argv.insert(1, "run")

    args = parser.parse_args()
    
    # Initialize logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level=log_level, log_file=args.log_file)
    
    if args.command == "export-schema":
        export_schemas()
    elif args.command == "install":
        from ledgermind.server.installers import install_client
        install_client(args.client, args.path)
    elif args.command == "bridge-context":
        bridge_context(args.path, args.prompt, args.cli, args.threshold)
    elif args.command == "bridge-record":
        bridge_record(args.path, args.prompt, args.response, args.success, args.metadata, args.cli)
    elif args.command == "init":
        init_project(args.path)
    elif args.command == "check":
        check_project(args.path)
    elif args.command == "stats":
        show_stats(args.path)
    elif args.command == "run":
        capabilities = None
        if args.capabilities:
            try:
                capabilities = json.loads(args.capabilities)
            except json.JSONDecodeError:
                print(f"Error: Invalid JSON for capabilities: {args.capabilities}")
                return

        from ledgermind.core.core.schemas import TrustBoundary
        from ledgermind.core.api.memory import Memory
        import signal
        import sys
        
        memory = MCPServer.memory_instance_for_cli = None # Placeholder for signal handler access

        def signal_handler(sig, frame):
            print("\nInterrupt received, shutting down...")
            if MCPServer.current_instance:
                MCPServer.current_instance.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        memory = Memory(storage_path=args.path, trust_boundary=TrustBoundary.AGENT_WITH_INTENT, vector_workers=args.vector_workers)
        server = MCPServer(
            memory, 
            server_name=args.name, 
            storage_path=args.path,
            capabilities=capabilities,
            metrics_port=args.metrics_port,
            rest_port=args.rest_port
        )
        MCPServer.current_instance = server
        server.run()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
