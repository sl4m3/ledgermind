"""Knowledge phase values."""

from enum import Enum


class Phase(str, Enum):
    PATTERN = "pattern"
    EMERGENT = "emergent"
    CANONICAL = "canonical"


__all__ = ["Phase"]
