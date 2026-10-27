"""Target adapter interface independent of the central installer."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..errors import AdapterError
from ..models import InstallerConfig
from ..paths import InstallerPaths


@dataclass(frozen=True, slots=True)
class TargetDiscovery:
    target_id: str
    label: str
    detected: bool
    home: Path | None = None
    config_dir: Path | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "target": self.target_id,
            "label": self.label,
            "detected": self.detected,
            "home": str(self.home) if self.home else None,
            "config_dir": str(self.config_dir) if self.config_dir else None,
            "detail": self.detail,
        }


@dataclass(slots=True)
class AdapterContext:
    config: InstallerConfig
    paths: InstallerPaths
    bundle_root: Path | None = None
    discovery: TargetDiscovery | None = None
    dry_run: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class TargetAdapter(Protocol):
    id: str
    label: str

    def discover(self) -> TargetDiscovery: ...

    def preflight(self, context: AdapterContext) -> dict[str, Any]: ...

    def install(self, context: AdapterContext) -> dict[str, Any]: ...

    def configure(self, context: AdapterContext) -> dict[str, Any]: ...

    def register_hooks(self, context: AdapterContext) -> dict[str, Any]: ...

    def verify(self, context: AdapterContext) -> dict[str, Any]: ...

    def repair(self, context: AdapterContext) -> dict[str, Any]: ...

    def uninstall(
        self, context: AdapterContext, *, purge: bool = False
    ) -> dict[str, Any]: ...

    def runtime_environment(self, context: AdapterContext) -> dict[str, str]: ...


class BaseTargetAdapter:
    id = "base"
    label = "Target"

    def discover(self) -> TargetDiscovery:
        raise AdapterError("target discovery is not implemented")

    def preflight(self, context: AdapterContext) -> dict[str, Any]:
        del context
        return {}

    def install(self, context: AdapterContext) -> dict[str, Any]:
        del context
        raise AdapterError("target installation is not implemented")

    def configure(self, context: AdapterContext) -> dict[str, Any]:
        del context
        return {}

    def register_hooks(self, context: AdapterContext) -> dict[str, Any]:
        del context
        return {}

    def verify(self, context: AdapterContext) -> dict[str, Any]:
        del context
        return {"status": "skipped"}

    def repair(self, context: AdapterContext) -> dict[str, Any]:
        return self.install(context)

    def uninstall(
        self, context: AdapterContext, *, purge: bool = False
    ) -> dict[str, Any]:
        del context, purge
        return {"status": "skipped"}

    def runtime_environment(self, context: AdapterContext) -> dict[str, str]:
        del context
        return {}


__all__ = ["AdapterContext", "BaseTargetAdapter", "TargetAdapter", "TargetDiscovery"]
