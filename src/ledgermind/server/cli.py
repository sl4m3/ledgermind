import argparse
import os
import json
import logging
import questionary
from typing import Optional, List, Dict, Any
from ledgermind.server.server import MCPServer
from ledgermind.core.utils.logging import setup_logging

def export_schemas():
    """Outputs the formal industrial-grade API specification."""
    from ledgermind.server.specification import MCPApiSpecification
    spec = MCPApiSpecification.generate_full_spec()
    print(json.dumps(spec, indent=2))

def init_project(path: str):
    """Interactive initialization of Ledgermind."""
    from rich.console import Console
    from rich.panel import Panel
    from ledgermind.core.api.memory import Memory
    from ledgermind.server.installers import install_client

    console = Console()
    console.print(Panel("[bold cyan]Welcome to LedgerMind Setup[/bold cyan]", expand=False))

    # 1. Project Path
    console.print("\n[bold yellow]Step 1: Project Location[/bold yellow]")
    console.print("Where is the codebase for this agent? (Hooks will be installed here)")
    project_path = questionary.text("Project Path:", default=os.getcwd()).ask()
    if project_path is None: return
    project_path = os.path.abspath(project_path)

    # 2. Memory Path
    console.print("\n[bold yellow]Step 2: Knowledge Core Location[/bold yellow]")
    console.print("Where should the memory database be stored?")
    console.print("We recommend placing it outside the project root (e.g., ../.ledgermind)")
    default_mem_path = os.path.abspath(os.path.join(project_path, "..", ".ledgermind"))
    custom_path = questionary.text("Memory Path:", default=default_mem_path).ask()
    if custom_path is None: return
    
    # 3. Embedder
    console.print("\n[bold yellow]Step 3: Embedding Model[/bold yellow]")
    console.print("LedgerMind uses a vector engine to semantically search your memory.")
    console.print("By default, we recommend the lightweight Jina v5 4-bit model (~60MB).")
    embedder = questionary.select(
        "Choose embedder:",
        choices=["jina-v5-4bit", "custom"],
        default="jina-v5-4bit"
    ).ask()
    if embedder is None: return
    
    model_name = "v5-small-text-matching-Q4_K_M.gguf"
    custom_url = None
    
    if embedder == "custom":
        console.print("You can provide a direct URL to a .gguf file to download it now,")
        console.print("OR provide an absolute path to an already downloaded .gguf file.")
        user_input = questionary.text("Enter URL or absolute path:").ask()
        if user_input is None: return
        
        if user_input.startswith("http://") or user_input.startswith("https://"):
            custom_url = user_input
            model_name = os.path.basename(custom_url.split("?")[0])
            if not model_name.endswith(".gguf"):
                model_name += ".gguf"
        else:
            model_name = user_input # Treat as absolute path or standard HF name

    # 4. Client
    console.print("\n[bold yellow]Step 4: Client Hooks[/bold yellow]")
    console.print(f"We can install hooks to seamlessly capture context for your preferred client in {project_path}.")
    client = questionary.select(
        "Which client do you use?",
        choices=["cursor", "claude", "gemini", "vscode", "none"],
        default="none"
    ).ask()
    if client is None: return
    
    # 5. Arbitration Mode
    console.print("\n[bold yellow]Step 5: Arbitration Mode[/bold yellow]")
    console.print("How should LedgerMind resolve memory conflicts and summarize knowledge?")
    console.print("  [bold]lite[/bold]    - Algorithmic resolution only (Fast, no LLM required)")
    console.print("  [bold]optimal[/bold] - Local LLM via Ollama/DeepSeek (Private, medium speed)")
    console.print("  [bold]rich[/bold]    - Cloud LLM via client (Highest quality, uses API)")
    mode = questionary.select(
        "Select mode:",
        choices=["lite", "optimal", "rich"],
        default="lite"
    ).ask()
    if mode is None: return

    # Initialize
    console.print("\n[bold green]Initializing system...[/bold green]")
    try:
        if os.path.isabs(model_name):
            model_path = model_name
            if not os.path.exists(model_path):
                 console.print(f"[yellow]Warning: Custom model path does not exist yet: {model_path}[/yellow]")
        else:
            model_path = os.path.join(custom_path, "models", model_name) if model_name.endswith(".gguf") else model_name
        
        # Ensure memory directory exists first
        os.makedirs(custom_path, exist_ok=True)
        os.makedirs(os.path.join(custom_path, "models"), exist_ok=True)

        if custom_url:
            console.print(f"Downloading custom model from {custom_url}...")
            import httpx
            import time
            try:
                with open(model_path, "wb") as f:
                    with httpx.stream("GET", custom_url, follow_redirects=True, timeout=60.0) as response:
                        response.raise_for_status()

                        total = int(response.headers.get("Content-Length", 0))
                        downloaded = 0
                        last_log = time.time()
                        for chunk in response.iter_bytes(chunk_size=1024*1024):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if time.time() - last_log > 2.0:
                                pct = (downloaded / total * 100) if total > 0 else 0
                                console.print(f"  Downloading... {pct:.1f}% ({downloaded/(1024*1024):.1f}MB)")
                                last_log = time.time()
                console.print(f"[green]✓ Downloaded to {model_path}[/green]")
            except Exception as e:
                console.print(f"[bold red]✗ Failed to download custom model: {e}[/bold red]")
                if os.path.exists(model_path): os.remove(model_path)
                return

        if embedder == "jina-v5-4bit" or model_name.endswith(".gguf"):
            try:
                from ledgermind.core.stores.vector import _is_llama_available
                if not _is_llama_available():
                    console.print("[red]Warning: llama-cpp-python is not installed. GGUF model might not work optimally until it's installed.[/red]")
            except ImportError:
                pass

        # Create memory structure. VectorStore init will auto-download GGUF if missing and URL is known.
        memory = Memory(storage_path=custom_path, vector_model=model_path)
        
        # Save Arbitration Mode and Client to config
        memory.semantic.meta.set_config("arbitration_mode", mode)
        memory.semantic.meta.set_config("client", client)

        console.print(f"[green]✓ Created memory structure at {custom_path}[/green]")
        console.print(f"[green]✓ Configured vector model: {model_name}[/green]")
        console.print(f"[green]✓ Set arbitration mode: {mode}[/green]")
        console.print(f"[green]✓ Registered client: {client}[/green]")

        if client != "none":
            console.print(f"\nInstalling hooks for {client} in {project_path}...")
            try:
                success = install_client(client, project_path)
                if success:
                    console.print(f"[green]✓ Hooks installed for {client}[/green]")
                else:
                    console.print(f"[bold red]✗ Failed to install hooks for {client}[/bold red]")
            except Exception as e:
                console.print(f"[yellow]Hook installer for '{client}' failed: {e}[/yellow]")

    except Exception as e:
        console.print(f"[bold red]✗ Error during initialization:[/bold red] {e}")
        import traceback
        console.print(traceback.format_exc())
        return

    console.print("\n[bold cyan]Initialization complete![/bold cyan]")
    console.print("You can now start the server with:")
    console.print(f"  ledgermind run --path {custom_path}")


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

def bridge_context(path: str, prompt: str, cli: Optional[str] = None, threshold: Optional[float] = None, read_stdin: bool = False):
    """Bridge API: Returns context for a prompt without starting MCP server."""
    from ledgermind.core.api.bridge import IntegrationBridge
    import sys
    import json
    try:
        real_prompt = prompt
        # 1. Handle stdin if requested
        if read_stdin or prompt == "-":
            if not sys.stdin.isatty():
                raw_input = sys.stdin.read()
                if raw_input:
                    try:
                        data = json.loads(raw_input)
                        if isinstance(data, dict):
                            real_prompt = data.get("userInput", data.get("prompt", raw_input))
                        else:
                            real_prompt = raw_input
                    except json.JSONDecodeError:
                        real_prompt = raw_input
        # 2. Handle JSON in prompt argument
        else:
            try:
                data = json.loads(prompt)
                if isinstance(data, dict):
                    real_prompt = data.get("userInput", data.get("prompt", prompt))
            except json.JSONDecodeError:
                pass

        default_cli = [cli] if cli else None
        bridge = IntegrationBridge(memory_path=path, default_cli=default_cli, relevance_threshold=threshold if threshold is not None else 0.7)
        
        # Record the prompt BEFORE fetching context
        if real_prompt and real_prompt != "-":
             bridge.memory.process_event(source="user", kind="prompt", content=real_prompt)
        
        ctx = bridge.get_context_for_prompt(real_prompt)
        sys.stdout.write(ctx)
    except Exception as e:
        sys.stderr.write(f"✗ Error: {e}\n")

def bridge_record(path: str, prompt: str, response: str, success: bool, metadata: str, cli: Optional[str] = None, read_stdin: bool = False):
    """Bridge API: Records interaction into episodic memory."""
    from ledgermind.core.api.bridge import IntegrationBridge
    import json
    import sys
    try:
        real_prompt = prompt
        real_response = response
        real_meta = json.loads(metadata) if metadata else {}
        real_success = success

        # Read from stdin if requested or if prompt/response are placeholders
        if read_stdin or (prompt == "Automated tool execution" and response == "-"):
            if not sys.stdin.isatty():
                try:
                    raw_input = sys.stdin.read()
                    if raw_input:
                        data = json.loads(raw_input)
                        if isinstance(data, dict):
                            # Try to extract from Claude Code PostToolUse format
                            if "toolUse" in data:
                                tool_name = data["toolUse"].get("name", "unknown")
                                tool_input = json.dumps(data["toolUse"].get("input", {}), ensure_ascii=False)
                                real_prompt = f"Tool Execution: {tool_name}"
                                real_response = f"Args: {tool_input}"
                                if "toolResult" in data:
                                    res = data["toolResult"].get("result", "")
                                    if not isinstance(res, str): res = json.dumps(res, ensure_ascii=False)
                                    real_response += f"\nResult: {res}"
                            
                            # Try to extract from general transcript/response format
                            elif "response" in data:
                                real_response = data["response"]
                                if "prompt" in data: real_prompt = data["prompt"]
                except Exception:
                    pass

        default_cli = [cli] if cli else None
        bridge = IntegrationBridge(memory_path=path, default_cli=default_cli)
        bridge.record_interaction(prompt=real_prompt, response=real_response, success=real_success, metadata=real_meta)
    except Exception as e:
        print(f"✗ Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="Ledgermind MCP Server Launcher")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run the MCP server")
    run_parser.add_argument("--path", default="../.ledgermind", help="Path to memory storage")
    run_parser.add_argument("--name", default="Ledgermind", help="MCP Server Name")
    run_parser.add_argument("--capabilities", help="JSON string of capabilities")
    run_parser.add_argument("--metrics-port", type=int, help="Port for Prometheus metrics")
    run_parser.add_argument("--rest-port", type=int, help="Port for REST Gateway")
    run_parser.add_argument("--vector-workers", type=int, default=0, help="Number of workers for multi-process encoding (0=auto)")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize a new memory project")
    init_parser.add_argument("--path", default="../.ledgermind", help="Path to create memory storage")

    # Check command
    check_parser = subparsers.add_parser("check", help="Check project health")
    check_parser.add_argument("--path", default="../.ledgermind", help="Path to memory storage")

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show memory statistics")
    stats_parser.add_argument("--path", default="../.ledgermind", help="Path to memory storage")

    # Install hooks command
    install_parser = subparsers.add_parser("install", help="Install LedgerMind hooks into a client")
    install_parser.add_argument("client", choices=["claude", "cursor", "gemini"], help="Target client to install hooks for")
    install_parser.add_argument("--path", default=os.getcwd(), help="Current project path to bind hooks to")

    # Bridge commands
    bc_parser = subparsers.add_parser("bridge-context", help="Internal: get context")
    bc_parser.add_argument("--path", default="../.ledgermind", help="Path to memory storage")
    bc_parser.add_argument("--prompt", required=True, help="User prompt")
    bc_parser.add_argument("--cli", help="Default CLI for arbitration")
    bc_parser.add_argument("--threshold", type=float, help="Relevance threshold")
    bc_parser.add_argument("--stdin", action="store_true", help="Read from stdin")

    br_parser = subparsers.add_parser("bridge-record", help="Internal: record interaction")
    br_parser.add_argument("--path", default="../.ledgermind", help="Path to memory storage")
    br_parser.add_argument("--prompt", required=True, help="User prompt")
    br_parser.add_argument("--response", required=True, help="Agent response")
    br_parser.add_argument("--success", action="store_true", default=True, help="Was successful")
    br_parser.add_argument("--metadata", default=None, help="JSON metadata")
    br_parser.add_argument("--cli", help="Default CLI for arbitration")
    br_parser.add_argument("--stdin", action="store_true", help="Read from stdin")

    # Global options
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--log-file", help="Path to log file")

    # Export schema command
    subparsers.add_parser("export-schema", help="Export JSON schemas for API contracts")

    # Default to 'run' if no command is provided
    import sys
    known_commands = ["run", "init", "check", "stats", "export-schema", "install", "bridge-context", "bridge-record", "-h", "--help", "--verbose", "-v", "--log-file"]
    if len(sys.argv) > 1 and sys.argv[1] not in known_commands:
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
        bridge_context(args.path, args.prompt, args.cli, args.threshold, args.stdin)
    elif args.command == "bridge-record":
        bridge_record(args.path, args.prompt, args.response, args.success, args.metadata, args.cli, args.stdin)
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
