from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

# --- API Versioning ---
MCP_API_VERSION = "2.4.3"

# --- Request Models ---

class RecordDecisionRequest(BaseModel):
    title: str = Field(..., min_length=1, description="Short title of the decision")
    target: str = Field(..., min_length=1, description="The object or area this decision applies to")
    rationale: str = Field(..., min_length=10, description="Detailed explanation of why this decision was made")
    consequences: List[str] = Field(default_factory=list, description="List of rules or effects resulting from this decision")

class SupersedeDecisionRequest(BaseModel):
    title: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=15)
    old_decision_ids: List[str] = Field(..., min_length=1, description="IDs of decisions to be superseded")
    consequences: List[str] = Field(default_factory=list)

class SearchDecisionsRequest(BaseModel):
    query: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=20)
    mode: Literal["strict", "balanced", "audit"] = Field(
        default="balanced", 
        description="strict: only active; balanced: active preferred; audit: all history"
    )

class AcceptProposalRequest(BaseModel):
    proposal_id: str = Field(..., description="The filename of the proposal to accept")

class SyncGitHistoryRequest(BaseModel):
    repo_path: str = Field(default=".", description="Path to the git repository to sync")
    limit: int = Field(default=20, ge=1, le=100, description="Max number of recent commits to index")

# --- Response Models ---

class BaseResponse(BaseModel):
    status: Literal["success", "error"]
    message: Optional[str] = None

class DecisionResponse(BaseResponse):
    decision_id: Optional[str] = None

class SearchResultItem(BaseModel):
    id: str
    score: float
    status: str
    preview: str
    kind: str

class SearchResponse(BaseResponse):
    results: List[SearchResultItem] = Field(default_factory=list)

class SyncGitResponse(BaseResponse):
    indexed_commits: int = 0
