from typing import Protocol, List, Dict, Any, Optional, runtime_checkable

@runtime_checkable
class MemoryProvider(Protocol):
    """
    Protocol defining the interface for memory providers (Core Memory or MCP Client).
    """
    
    def record_decision(self, title: str, target: str, rationale: str, consequences: Optional[List[str]] = None) -> Any:
        """Records a new decision."""
        ...
    
    def supersede_decision(self, title: str, target: str, rationale: str, old_decision_ids: List[str], consequences: Optional[List[str]] = None) -> Any:
        """Supersedes existing decisions."""
        ...
        
    def search_decisions(self, query: str, limit: int = 5, mode: str = "balanced") -> List[Dict[str, Any]]:
        """Searches for decisions."""
        ...
        
    def accept_proposal(self, proposal_id: str) -> Any:
        """Accepts a proposal."""
        ...

    def sync_git(self, repo_path: str = ".", limit: int = 20) -> Any:
        """Syncs git history."""
        ...
