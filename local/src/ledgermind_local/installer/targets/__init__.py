"""Target adapter registry."""

from .base import TargetAdapter, TargetDiscovery
from .registry import get_target_adapter, target_ids

__all__ = ["TargetAdapter", "TargetDiscovery", "get_target_adapter", "target_ids"]
