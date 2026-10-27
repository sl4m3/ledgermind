"""Stable machine-readable installer results."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ExitCode


def _json_safe(value: Any) -> Any:
    """Normalize result metadata before it reaches either CLI renderer.

    Installer operations may legitimately return paths discovered or created
    during a transaction.  Keeping those values as ``Path`` objects inside
    Python is useful, but the public result contract is JSON and must never
    turn a successfully committed install into a failing CLI invocation.
    """

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


@dataclass(slots=True)
class ResultStep:
    name: str
    status: str
    detail: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name, "status": self.status}
        if self.detail:
            result["detail"] = self.detail
        if self.data:
            result["data"] = _json_safe(self.data)
        return result


@dataclass(slots=True)
class InstallResult:
    operation: str
    exit_code: ExitCode = ExitCode.SUCCESS
    status: str = "success"
    steps: list[ResultStep] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    paths: dict[str, Any] = field(default_factory=dict)
    profiles: list[dict[str, Any]] = field(default_factory=list)
    runtime: dict[str, Any] = field(default_factory=dict)
    smoke_test: dict[str, Any] = field(default_factory=dict)

    def step(
        self,
        name: str,
        status: str,
        detail: str | None = None,
        **data: Any,
    ) -> None:
        self.steps.append(ResultStep(name, status, detail, data))

    def warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)
        self.status = "failed"

    def fail(self, code: ExitCode, message: str) -> InstallResult:
        self.exit_code = code
        self.error(message)
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "operation": self.operation,
            "exit_code": int(self.exit_code),
            "steps": [step.as_dict() for step in self.steps],
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "paths": _json_safe(self.paths),
            "profiles": _json_safe(self.profiles),
            "runtime": _json_safe(self.runtime),
            "smoke_test": _json_safe(self.smoke_test),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)


__all__ = ["InstallResult", "ResultStep"]
