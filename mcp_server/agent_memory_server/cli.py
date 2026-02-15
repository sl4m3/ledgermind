import argparse
import os
import json
from agent_memory_server.server import MCPServer

def export_schemas():
    """Outputs JSON schemas for all MCP tool contracts."""
    from agent_memory_server import contracts
    import pydantic
    
    schemas = {
        "version": contracts.MCP_API_VERSION,
        "models": {
            "RecordDecisionRequest": contracts.RecordDecisionRequest.model_json_schema(),
            "SupersedeDecisionRequest": contracts.SupersedeDecisionRequest.model_json_schema(),
            "SearchDecisionsRequest": contracts.SearchDecisionsRequest.model_json_schema(),
            "AcceptProposalRequest": contracts.AcceptProposalRequest.model_json_schema(),
            "SearchResponse": contracts.SearchResponse.model_json_schema(),
            "BaseResponse": contracts.BaseResponse.model_json_schema(),
        }
    }
    print(json.dumps(schemas, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Agent Memory MCP Server Launcher")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Run command (default)
    run_parser = subparsers.add_parser("run", help="Run the MCP server")
    run_parser.add_argument("--path", default=".agent_memory", help="Path to memory storage")
    run_parser.add_argument("--name", default="AgentMemory", help="MCP Server Name")
    run_parser.add_argument("--role", default="agent", choices=["viewer", "agent", "admin"], help="Authority role")
    
    # Export schema command
    subparsers.add_parser("export-schema", help="Export JSON schemas for API contracts")
    
    args = parser.parse_args()
    
    if args.command == "export-schema":
        export_schemas()
    else:
        # Default to run if no command specified (for backward compatibility)
        path = getattr(args, "path", ".agent_memory")
        name = getattr(args, "name", "AgentMemory")
        role = getattr(args, "role", "agent")
        
        MCPServer.serve(
            storage_path=path,
            server_name=name,
            role=role
        )

if __name__ == "__main__":
    main()
