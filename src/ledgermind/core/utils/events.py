import asyncio
import logging
from typing import Callable, Any, Dict, List

logger = logging.getLogger("ledgermind-core.events")

class EventEmitter:
    """Simple event emitter for internal memory events."""
    
    def __init__(self):
        self._subscribers: List[Callable[[str, Any], Any]] = []

    def subscribe(self, callback: Callable[[str, Any], Any]):
        """Registers a callback for all events."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[str, Any], Any]):
        """Unregisters a callback from events to prevent memory leaks."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def emit(self, event_type: str, data: Any):
        """Dispatches an event to all subscribers."""
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        for callback in self._subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    if loop and loop.is_running():
                        loop.create_task(callback(event_type, data))
                    else:
                        # Fallback for sync environments: we can't run async callbacks without a loop
                        # but we should not crash or log heavily if this is expected.
                        logger.debug(f"Skipping async subscriber {callback} for {event_type}: no running event loop.")
                else:
                    callback(event_type, data)
            except Exception as e:
                logger.error(f"Error in event subscriber: {e}")
