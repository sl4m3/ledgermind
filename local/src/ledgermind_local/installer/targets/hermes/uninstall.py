"""Hermes uninstall adapter entry point."""

from __future__ import annotations

from pathlib import Path

from .install import restore_plugin


def uninstall_plugin(
    hermes_home: str | Path, *, purge: bool = False
) -> dict[str, object]:
    root = Path(hermes_home).expanduser() / "plugins" / "ledgermind-hermes"
    return restore_plugin(plugin_root=root, purge=purge)


__all__ = ["uninstall_plugin"]
