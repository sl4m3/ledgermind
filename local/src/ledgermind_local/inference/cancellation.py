"""Cancellation primitives shared by Local inference providers."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .providers.base import ProviderCancelledError


class CancellationToken:
    """Thread-safe cancellation signal with interruptible waiting."""

    def __init__(self, event: threading.Event | None = None) -> None:
        self._event = event or threading.Event()

    @property
    def cancelled(self) -> bool:
        return self.is_cancelled()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for cancellation and return whether cancellation was observed."""

        if timeout is not None and timeout < 0:
            raise ValueError("cancellation wait timeout must not be negative")
        return self._event.wait(timeout)

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled():
            # Import lazily so the provider error remains the canonical subclass
            # of ProviderError without introducing a module import cycle.
            from .providers.base import ProviderCancelledError

            raise ProviderCancelledError()


def __getattr__(name: str) -> object:
    """Lazily re-export the provider error without an import cycle."""

    if name == "ProviderCancelledError":
        from .providers.base import ProviderCancelledError

        return ProviderCancelledError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["CancellationToken", "ProviderCancelledError"]
