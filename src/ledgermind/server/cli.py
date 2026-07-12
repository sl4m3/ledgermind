import argparse
import os
import json
import logging
import sys

logger = logging.getLogger("ledgermind.cli")
from typing import Optional


# Redirect all CLI info/errors to stderr so we don't corrupt stdout for bridge hooks
try:
    from rich.console import Console
    global_console = Console(stderr=True)
except ImportError:
    global_console = None


def export_schemas():
    """Outputs the formal industrial-grade API specification."""
    from ledgermind.server.specification import MCPApiSpecification

    spec = MCPApiSpecification.generate_full_spec()
    print(json.dumps(spec, indent=2))


def run_server(path: str = ".ledgermind"):
    """Run the MCP server."""
    from ledgermind.server.server import MCPServer
    server = MCPServer(storage_path=path)
    server.run()


def install_hermes(args):
    """Install LedgerMind plugin for Hermes."""
    from ledgermind.server.installers import install_hermes as do_install, install_interactive

    # Check if any flags were provided (beyond the client name)
    has_flags = any([
        args.mode != "agent",
        args.enrichment != "openrouter",
        args.api_key is not None,
        args.base_url is not None,
        args.language != "english",
    ])

    if args.interactive or not has_flags:
        result = install_interactive()
    else:
        result = do_install(
            mode=args.mode,
            enrichment=args.enrichment,
            api_key=args.api_key,
            base_url=args.base_url,
            language=args.language,
        )

    # Print results
    for msg in result.get("messages", []):
        print(f"  ✓ {msg}", file=sys.stderr)
    for err in result.get("errors", []):
        print(f"  ✗ {err}", file=sys.stderr)

    if result["success"]:
        print("\nDone! LedgerMind plugin installed for Hermes.", file=sys.stderr)
        print("Restart Hermes to activate.", file=sys.stderr)
    else:
        print("\nInstallation failed.", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="LedgerMind - Autonomous Memory for AI Agents")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Install
    install_parser = subparsers.add_parser("install", help="Install plugin for a client")
    install_parser.add_argument("client", choices=["hermes"], help="Client to install for")
    install_parser.add_argument("--mode", default="agent", choices=["agent", "core"],
                                help="Operating mode (agent=structured summaries, core=raw pipeline)")
    install_parser.add_argument("--enrichment", default="openrouter",
                                choices=["openrouter", "nvidia", "aistudio", "custom"],
                                help="Enrichment model provider")
    install_parser.add_argument("--api-key", default=None, help="API key for enrichment provider")
    install_parser.add_argument("--base-url", default=None, help="Base URL for enrichment provider")
    install_parser.add_argument("--language", default="english", help="Language for enrichment (english, russian, etc)")
    install_parser.add_argument("--interactive", "-i", action="store_true", help="Force interactive mode")

    # Run server
    run_parser = subparsers.add_parser("run", help="Run MCP server")
    run_parser.add_argument("--path", default=".ledgermind", help="Memory path")

    # Serve (FastAPI)
    serve_parser = subparsers.add_parser("serve", help="Run HTTP API server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    serve_parser.add_argument("--port", type=int, default=8000, help="Bind port")

    # Export schemas
    subparsers.add_parser("schemas", help="Export API schemas")

    args = parser.parse_args()

    if args.command == "install":
        if args.client == "hermes":
            install_hermes(args)
        else:
            print(f"Client '{args.client}' not supported yet.", file=sys.stderr)
            sys.exit(1)
    elif args.command == "run":
        run_server(args.path)
    elif args.command == "serve":
        from ledgermind.server.api import run_server as run_api
        run_api(host=args.host, port=args.port)
    elif args.command == "schemas":
        export_schemas()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
