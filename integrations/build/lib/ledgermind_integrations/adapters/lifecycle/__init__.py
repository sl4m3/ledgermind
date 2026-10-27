"""Shared lifecycle bridge used by command- and plugin-based agent adapters."""

from .bridge import handle_hook
from .config import LifecycleConfig, load_lifecycle_config

__all__ = ["LifecycleConfig", "handle_hook", "load_lifecycle_config"]
