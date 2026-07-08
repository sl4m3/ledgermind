import argparse
import os
import json
import logging
import sys

logger = logging.getLogger("ledgermind.cli")
from typing import Optional
from ledgermind.server.server import MCPServer
from ledgermind.core.utils.logging import setup_logging


from rich.console import Console

# Redirect all CLI info/errors to stderr so we don't corrupt stdout for bridge hooks
global_console = Console(stderr=True)


def export_schemas():
    """Outputs the formal industrial-grade API specification."""
    from ledgermind.server.specification import MCPApiSpecification

    spec = MCPApiSpecification.generate_full_spec()
    print(json.dumps(spec, indent=2))


def run_server(path: str = ".ledgermind"):
    """Run the MCP server."""
    server = MCPServer(storage_path=path)
    server.run()


def bridge_context(path: str, prompt: str, cli: str = "hermes", stdin: bool = False):
    """Bridge context for integration with Hermes/OpenClaw."""
    from ledgermind.core.api.bridge import Bridge

    if stdin:
        prompt = sys.stdin.read().strip()

    bridge = Bridge(memory_path=path, namespace=cli)
    context = bridge.get_context_for_prompt(prompt)
    if context:
        print(context)


def bridge_sync(path: str, cli: str = "hermes", stdin: bool = False):
    """Bridge sync for recording interactions."""
    from ledgermind.core.api.bridge import Bridge

    if stdin:
        data = sys.stdin.read().strip()
    else:
        data = ""

    bridge = Bridge(memory_path=path, namespace=cli)
    if data:
        bridge.record_interaction("user", data, success=True)


def main():
    parser = argparse.ArgumentParser(description="LedgerMind - Autonomous Memory for AI Agents")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Run server
    run_parser = subparsers.add_parser("run", help="Run MCP server")
    run_parser.add_argument("--path", default=".ledgermind", help="Memory path")

    # Export schemas
    subparsers.add_parser("schemas", help="Export API schemas")

    # Bridge context
    bridge_context_parser = subparsers.add_parser("bridge-context", help="Bridge context for prompt")
    bridge_context_parser.add_argument("--path", required=True, help="Memory path")
    bridge_context_parser.add_argument("--prompt", required=True, help="User prompt")
    bridge_context_parser.add_argument("--cli", default="hermes", help="CLI name (hermes/openclaw)")
    bridge_context_parser.add_argument("--stdin", action="store_true", help="Read prompt from stdin")

    # Bridge sync
    bridge_sync_parser = subparsers.add_parser("bridge-sync", help="Bridge sync for recording")
    bridge_sync_parser.add_argument("--path", required=True, help="Memory path")
    bridge_sync_parser.add_argument("--cli", default="hermes", help="CLI name (hermes/openclaw)")
    bridge_sync_parser.add_argument("--stdin", action="store_true", help="Read data from stdin")

    args = parser.parse_args()

    if args.command == "run":
        run_server(args.path)
    elif args.command == "schemas":
        export_schemas()
    elif args.command == "bridge-context":
        bridge_context(args.path, args.prompt, args.cli, args.stdin)
    elif args.command == "bridge-sync":
        bridge_sync(args.path, args.cli, args.stdin)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
