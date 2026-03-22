from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from abc import ABC, abstractmethod

from ledgermind.core.core.schemas import MemoryEvent

class EpisodicProvider(ABC):
    @abstractmethod
    def append(self, event: MemoryEvent, linked_id: Optional[str] = None) -> int:
        pass

    @abstractmethod
    def link_to_semantic(self, event_id: int, semantic_id: str):
        pass

    @abstractmethod
    def link_to_semantic_batch(self, event_ids: List[int], semantic_id: str, strength: float = 1.0):
        pass

    @abstractmethod
    def query(self, limit: int = 100, status: Optional[str] = 'active') -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def count_links_for_semantic(self, semantic_id: str) -> Tuple[int, float]:
        pass

    @abstractmethod
    def count_links_for_semantic_batch(self, semantic_ids: List[str]) -> Dict[str, Tuple[int, float]]:
        pass

    @abstractmethod
    def mark_archived(self, event_ids: List[int]):
        pass

    @abstractmethod
    def physical_prune(self, event_ids: List[int]):
        pass

    @abstractmethod
    def get_linked_event_ids_batch(self, semantic_ids: List[str]) -> Dict[str, List[int]]:
        pass

class AuditProvider(ABC):
    @abstractmethod
    def initialize(self):
        pass

    @abstractmethod
    def add_artifact(self, relative_path: str, content: str, commit_msg: str):
        pass

    @abstractmethod
    def update_artifact(self, relative_path: str, content: str, commit_msg: str):
        pass

    @abstractmethod
    def get_head_hash(self) -> Optional[str]:
        pass

    @abstractmethod
    def purge_artifact(self, relative_path: str):
        pass

    @abstractmethod
    def commit_transaction(self, message: str):
        pass

    @abstractmethod
    def get_history(self, relative_path: str) -> List[Dict[str, Any]]:
        pass

class MetadataStore(ABC):
    @abstractmethod
    def get_version(self) -> str:
        pass

    @abstractmethod
    def set_version(self, version: str):
        pass

    @abstractmethod
    def upsert(self, fid: str, target: str, title: str = "Untitled", status: str = "active", kind: str = "decision", 
               timestamp: Any = None, content: str = "", context_json: str = "{}", 
               namespace: str = "default", phase: str = "pattern", 
               vitality: str = "active", enrichment_status: str = "pending",
               **kwargs):
        pass

    @abstractmethod
    def batch_update(self, updates: Optional[List[Tuple[str, Dict[str, Any]]]] = None):
        pass

    @abstractmethod
    def update_status(self, fid: str, status: str):
        pass

    @abstractmethod
    def get_by_fid(self, fid: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_active_fid(self, target: str, namespace: str = "default") -> Optional[str]:
        pass

    @abstractmethod
    def get_active_fids_by_base_target(self, base_target: str, namespace: str = "default") -> List[str]:
        pass

    @abstractmethod
    def resolve_to_truth(self, doc_id: str, cache: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def list_all(self, namespace: Optional[str] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def keyword_search(self, query: str, limit: int = 10, namespace: str = "default", status: Optional[str] = None) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def increment_hit(self, fid: str):
        pass

    @abstractmethod
    def delete(self, fid: str):
        pass

    @abstractmethod
    def clear(self):
        pass

    @abstractmethod
    def get_config(self, key: str, default: Any = None) -> Any:
        pass

    @abstractmethod
    def set_config(self, key: str, value: Any):
        pass

    @abstractmethod
    def close(self):
        pass

