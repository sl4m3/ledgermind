from dataclasses import dataclass
from typing import Any, Optional, Union
from ledgermind.core.core.schemas import LedgermindConfig, TrustBoundary
from ledgermind.core.stores.episodic import EpisodicStore
from ledgermind.core.stores.semantic import SemanticStore
from ledgermind.core.stores.vector import VectorStore
from ledgermind.core.stores.interfaces import EpisodicProvider

@dataclass
class MemoryContext:
    """
    Shared runtime context for LedgerMind memory services.
    Provides access to storage engines, configuration, and state.
    """
    storage_path: str
    namespace: str
    trust_boundary: TrustBoundary
    include_history: bool
    config: LedgermindConfig
    
    # Core Stores
    semantic: SemanticStore
    episodic: Union[EpisodicStore, EpisodicProvider]
    vector: VectorStore
    
    # Engines & Registry
    conflict_engine: Any
    resolution_engine: Any
    decay_engine: Any
    reflection_engine: Any
    targets: Any
    lifecycle: Any
    
    # Shared Transaction Manager (will be initialized by Memory)
    transaction_manager: Optional[Any] = None
