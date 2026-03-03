import json
from typing import Dict, Any, List
from ledgermind.server import contracts

class MCPApiSpecification:
    """
    Formal specification generator for Agent Memory MCP API.
    Ensures that the interface is versioned and predictable.
    """
    API_VERSION = contracts.MCP_API_VERSION
    
    @classmethod
    def generate_full_spec(cls) -> Dict[str, Any]:
        """Generates a complete JSON specification of the API."""
        return {
            "mcp_api_version": cls.API_VERSION,
            "info": {
                "title": "Agent Memory MCP API",
                "description": "Formal contract for autonomous agent memory management.",
                "contact": "https://github.com/sl4m3/ledgermind"
            },
            "tools": {
                "record_decision": {
                    "description": "Records a strategic decision with rationale and consequences.",
                    "input_schema": contracts.RecordDecisionRequest.model_json_schema(),
                    "output_schema": contracts.DecisionResponse.model_json_schema()
                },
                "supersede_decision": {
                    "description": "Replaces existing decisions with a new one, maintaining graph integrity.",
                    "input_schema": contracts.SupersedeDecisionRequest.model_json_schema(),
                    "output_schema": contracts.DecisionResponse.model_json_schema()
                },
                "search_decisions": {
                    "description": "Hybrid semantic search with state-aware ranking.",
                    "input_schema": contracts.SearchDecisionsRequest.model_json_schema(),
                    "output_schema": contracts.SearchResponse.model_json_schema()
                },
                "accept_proposal": {
                    "description": "Promotes a draft proposal to an active decision (ADMIN only).",
                    "input_schema": contracts.AcceptProposalRequest.model_json_schema(),
                    "output_schema": contracts.BaseResponse.model_json_schema()
                },
                "sync_git_history": {
                    "description": "Syncs Git commit history into episodic memory for context.",
                    "input_schema": contracts.SyncGitHistoryRequest.model_json_schema(),
                    "output_schema": contracts.SyncGitResponse.model_json_schema()
                }
            },
            "errors": {
                "403": "Permission Denied: Missing or invalid AGENT_MEMORY_SECRET.",
                "409": "Conflict: Target already has an active decision (use supersede).",
                "422": "Validation Error: Schema mismatch.",
                "429": "Rate Limit: Cooldown violation."
            }
        }

    @classmethod
    def export_to_file(cls, path: str):
        spec = cls.generate_full_spec()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2)
