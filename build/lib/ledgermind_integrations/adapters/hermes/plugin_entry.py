"""Hermes plugin entry point."""

from __future__ import annotations

from .hook_contracts import HermesPluginContext
from .runtime import HermesPluginRuntime

_runtime: HermesPluginRuntime | None = None


def register(ctx: HermesPluginContext) -> None:
    global _runtime
    if _runtime is not None:
        _runtime.shutdown()
    _runtime = HermesPluginRuntime.from_context(ctx)
    if not _runtime.config.enabled:
        return
    _runtime.register_hooks(ctx)
    on_unload = getattr(ctx, "on_unload", None)
    if callable(on_unload):
        on_unload(_runtime.shutdown)


__all__ = ["register"]
