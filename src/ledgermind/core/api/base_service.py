from typing import Any
from .context import MemoryContext

class MemoryService:
    """
    Base class for LedgerMind memory services.
    Provides access to shared context and its core components.
    """
    def __init__(self, context: MemoryContext):
        self.context = context
        
    @property
    def semantic(self):
        return self.context.semantic
        
    @property
    def episodic(self):
        return self.context.episodic
        
    @property
    def vector(self):
        return self.context.vector
        
    @property
    def transaction_manager(self):
        return self.context.transaction_manager
        
    def transaction(self, description: str = ""):
        """Helper to access transaction manager."""
        return self.transaction_manager.transaction(description=description)
