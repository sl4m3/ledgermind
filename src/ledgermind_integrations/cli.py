"""CLI for installing LedgerMind client integrations."""

from __future__ import annotations

import argparse
import json
import sys

from .installer import install_hermes, uninstall_hermes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ledgermind-integrations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    install = subparsers.add_parser("install", help="install an integration")
    install_subparsers = install.add_subparsers(dest="adapter", required=True)
    hermes = install_subparsers.add_parser("hermes")
    hermes.add_argument("--destination", help="parent directory for the plugin")
    uninstall = subparsers.add_parser("uninstall", help="remove an integration")
    uninstall_subparsers = uninstall.add_subparsers(dest="adapter", required=True)
    hermes_uninstall = uninstall_subparsers.add_parser("hermes")
    hermes_uninstall.add_argument("--destination", help="parent directory for the plugin")
    hook = subparsers.add_parser("hook", help=argparse.SUPPRESS)
    hook.add_argument("--config", required=True)
    hook.add_argument("--event", required=True)
    args = parser.parse_args(argv)
    if args.command == "install" and args.adapter == "hermes":
        print(install_hermes(args.destination))
        return 0
    if args.command == "uninstall" and args.adapter == "hermes":
        print(uninstall_hermes(args.destination))
        return 0
    if args.command == "hook":
        from .adapters.lifecycle import handle_hook, load_lifecycle_config

        try:
            payload = json.load(sys.stdin)
            if not isinstance(payload, dict):
                payload = {}
            result = handle_hook(load_lifecycle_config(args.config), args.event, payload)
        except Exception:  # noqa: BLE001 -- agent hooks must fail open
            result = {}
        if result:
            print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        return 0
    parser.error("unsupported command")


if __name__ == "__main__":
    raise SystemExit(main())
