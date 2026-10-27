"""Small internal installer value objects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DownloadedArtifact:
    path: Path
    size: int
    sha256: str


__all__ = ["DownloadedArtifact"]
