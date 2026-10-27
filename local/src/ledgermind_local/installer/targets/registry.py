"""Central target registry."""

from __future__ import annotations

from .base import TargetAdapter
from .hermes.adapter import HermesTargetAdapter
from .lifecycle import (
    PLUGIN_SPECS,
    SPECS,
    LifecycleTargetAdapter,
    PluginTargetAdapter,
)

_ADAPTERS: dict[str, TargetAdapter] = {
    "hermes": HermesTargetAdapter(),
    **{spec.target_id: LifecycleTargetAdapter(spec) for spec in SPECS},
    **{spec.target_id: PluginTargetAdapter(spec) for spec in PLUGIN_SPECS},
}


def target_ids() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))


def get_target_adapter(target_id: str) -> TargetAdapter:
    try:
        return _ADAPTERS[target_id]
    except KeyError as exc:
        raise ValueError(f"unsupported target: {target_id}") from exc


__all__ = ["get_target_adapter", "target_ids"]
