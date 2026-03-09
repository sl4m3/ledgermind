import logging
import threading
from typing import Callable, TypeVar, Any, Generator
from contextlib import contextmanager

logger = logging.getLogger("ledgermind.core.api.transaction")

T = TypeVar('T')

class ReentrantTransactionManager:
    """
    Manages nested transactions using SQLite SAVEPOINTs.
    Ensures thread-safety and proper rollback/commit semantics for nested calls.
    """
    def __init__(self, semantic_store: Any):
        self.semantic = semantic_store
        self._transaction_depth = 0
        self._lock = threading.RLock()

    @contextmanager
    def transaction(self, description: str = "") -> Generator[None, None, None]:
        """
        Context manager for reentrant transactions.
        Delegates to the underlying SemanticStore which handles reentrancy natively.
        """
        if description:
            logger.debug(f"Starting transaction: {description}")

        with self.semantic.transaction():
            yield
    def execute(self, callback: Callable[..., T], *args, **kwargs) -> T:
        """Executes a callable within a transaction."""
        with self.transaction():
            return callback(*args, **kwargs)
