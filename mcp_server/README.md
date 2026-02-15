# Agent Memory Server

Dedicated MCP (Model Context Protocol) Server for the Agent Memory System.

## Features
- Provides a standardized interface for any AI model to access memory.
- Enforces process invariants (Review Window, Evidence Threshold).
- Includes environment context tools.

## Installation
```bash
pip install -e ./core -e ./mcp_server
```

## Running
```bash
agent-memory-mcp --path ./.agent_memory --name MyAgentMemory
```
