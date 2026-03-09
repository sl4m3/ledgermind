from typing import Protocol, Any, Dict, List, Generator, Optional
from contextlib import contextmanager
from dataclasses import dataclass

@dataclass
class Result:
    """Wrapper for operation results without throwing exceptions."""
    success: bool
    data: Any = None
    error: Optional[str] = None

class SemanticMetaProtocol(Protocol):
    def list_all(self) -> List[Dict[str, Any]]: ...

class SemanticStoreProtocol(Protocol):
    meta: SemanticMetaProtocol
    
    @contextmanager
    def transaction(self, description: str = "") -> Generator[None, None, None]: ...

    def add_decision(self, fid: str, data: Dict[str, Any], kind: str = "decision", commit_msg: str = "") -> None: ...
    
    def lock_decisions(self, fids: List[str], reason: str) -> None: ...
    
    def get_active_targets(self) -> List[str]: ...

class VectorIndexProtocol(Protocol):
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]: ...

class MemoryProtocol(Protocol):
    """Strict protocol for a memory object."""
    semantic: SemanticStoreProtocol
    vector_index: VectorIndexProtocol
