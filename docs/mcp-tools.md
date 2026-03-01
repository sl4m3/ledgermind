# MCP Tools

Complete reference for all 15 Model Context Protocol (MCP) tools available in LedgerMind.

---

## Introduction

This document provides detailed documentation for every MCP tool available in LedgerMind. Each tool includes:

- **Purpose**: What the tool does and when to use it
- **Parameters**: Input schema with types, defaults, and validation rules
- **Returns**: Response format and data structures
- **Examples**: Practical usage patterns
- **Error Handling**: Common failures and recovery strategies

**Audience**:
- **MCP Client Developers** integrating LedgerMind with Claude Desktop, Cursor, etc.
- **LLM Agents** calling tools via MCP protocol
- **System Administrators** configuring tool permissions and roles

**Quick Reference**:

| Tool | Category | Read/Write | Use Case |
|------|----------|-----------|----------|
| `bridge-context` | Integration | Read | Retrieve context for prompts |
| `bridge-record` | Integration | Write | Record interactions |
| `get_context_for_prompt` | Search | Read | Get semantic context |
| `record_decision` | Memory | Write | Create new decision |
| `supersede_decision` | Memory | Write | Replace old decision |
| `accept_proposal` | Memory | Write | Promote proposal to decision |
| `reject_proposal` | Memory | Write | Mark proposal as rejected |
| `search_decisions` | Search | Read | Find relevant decisions |
| `get_decisions` | Search | Read | Get decisions by filters |
| `get_decision_history` | Search | Read | Get decision evolution |
| `get_recent_events` | Search | Read | Get recent episodic events |
| `link_evidence` | Evidence | Write | Connect events to decisions |
| `update_decision` | Memory | Write | Update decision metadata |
| `sync_git` | Git | Write | Sync semantic memory to Git |
| `forget` | Memory | Write | Delete memories |

---

## Tool Categories

### Integration Tools

**Purpose**: High-level convenience tools for client-side integration. These tools are designed for IDE hooks and automated workflows.

### Memory Tools

**Purpose**: Core operations for managing semantic memory (decisions, proposals, constraints).

### Search Tools

**Purpose**: Querying both episodic and semantic memory with various filters.

### Evidence Tools

**Purpose**: Linking episodic events to semantic decisions for traceability.

### Git Tools

**Purpose**: Managing Git audit trail for semantic memory.

---

## Integration Tools

### bridge-context

Retrieve relevant context for a user's prompt. Used by IDE hooks to inject memory into LLM context.

**Purpose**: Get semantic decisions and procedural knowledge relevant to a query.

**Use Cases**:
- IDE hooks injecting context before AI responds
- Background workers gathering context for automation
- Multi-agent systems sharing knowledge

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "minLength": 1,
      "description": "User's prompt or query"
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 20,
      "default": 3,
      "description": "Maximum number of memories to retrieve"
    },
    "mode": {
      "type": "string",
      "enum": ["strict", "balanced", "fuzzy"],
      "default": "balanced",
      "description": "Search strictness"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace for multi-agent isolation"
    }
  },
  "required": ["query"]
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | — | User's prompt to get context for (required) |
| `limit` | integer | `3` | Max memories to retrieve (1-20) |
| `mode` | string | `"balanced"` | Search mode: `strict`, `balanced`, `fuzzy` |
| `namespace` | string | `"default"` | Memory namespace |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "source": {
      "type": "string",
      "enum": ["ledgermind"]
    },
    "memories": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "Decision ID (fid)"
          },
          "title": {
            "type": "string",
            "description": "Decision title"
          },
          "target": {
            "type": "string",
            "description": "Target system or component"
          },
          "score": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Relevance score (0.0-1.0)"
          },
          "status": {
            "type": "string",
            "enum": ["active", "superseded", "deprecated", "rejected", "draft"]
          },
          "kind": {
            "type": "string",
            "enum": ["decision", "proposal", "constraint"]
          },
          "path": {
            "type": "string",
            "description": "Absolute path to Markdown file"
          },
          "content": {
            "type": "string",
            "description": "Decision content preview"
          },
          "rationale": {
            "type": "string",
            "description": "Decision rationale"
          },
          "instruction": {
            "type": "string",
            "description": "Usage instruction for LLM"
          },
          "procedural_guide": {
            "type": "array",
            "items": {
              "type": "string"
            },
            "description": "Procedural knowledge steps"
          }
        }
      }
    }
  }
}
```

**Example Usage**:

```python
# Get context for a database question
result = client.call_tool("bridge-context", {
    "query": "How should I handle database migrations?",
    "limit": 3,
    "mode": "balanced",
    "namespace": "backend"
})

# Result:
{
  "source": "ledgermind",
  "memories": [
    {
      "id": "abc123",
      "title": "Use exponential backoff for retries",
      "target": "api_client",
      "score": 0.85,
      "status": "active",
      "kind": "decision",
      "path": "/home/user/.ledgermind/semantic/abc123.md",
      "content": "Use exponential backoff when retrying failed...",
      "rationale": "Prevents overwhelming server during outages.",
      "instruction": "Use 'cat /path/to/file.md' for full history.",
      "procedural_guide": ["1. Start with 1s delay", "2. Double each retry up to 10s max"]
    }
    // ... more memories
  ]
}
```

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `400 Bad Request` | Invalid query (empty) | Provide non-empty query string |
| `422 Unprocessable Entity` | Invalid parameter type | Check parameter types and constraints |

---

### bridge-record

Record an interaction with the memory system. Used by IDE hooks to capture AI responses and evidence.

**Purpose**: Record both prompt/response interactions and link them to relevant decisions.

**Use Cases**:
- IDE hooks recording AI responses after they complete
- Background workers logging automated actions
- Evidence collection for decision traceability

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "prompt": {
      "type": "string",
      "minLength": 1,
      "description": "User's prompt"
    },
    "response": {
      "type": "string",
      "minLength": 1,
      "description": "AI's response"
    },
    "success": {
      "type": "boolean",
      "default": true,
      "description": "Whether the operation was successful"
    },
    "metadata": {
      "type": "object",
      "description": "Additional context (tool used, duration, etc.)"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  },
  "required": ["prompt", "response"]
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | — | User's prompt (required) |
| `response` | string | — | AI's response (required) |
| `success` | boolean | `true` | Operation success flag |
| `metadata` | object | `{}` | Additional context (tool, duration, etc.) |
| `namespace` | string | `"default"` | Memory namespace |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "event_id": {
      "type": "string",
      "description": "Recorded event ID"
    },
    "linked_decisions": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Decision IDs that were linked as evidence"
    }
  }
}
```

**Example Usage**:

```python
# Record a successful API interaction
result = client.call_tool("bridge-record", {
    "prompt": "Test API endpoint",
    "response": "200 OK - Response received in 1.2s",
    "success": true,
    "metadata": {
        "tool_used": "http_client",
        "duration_seconds": 1.2,
        "endpoint": "/api/3.1.2/health"
    },
    "namespace": "backend"
})

# Result:
{
  "event_id": "evt_abc123",
  "linked_decisions": ["abc123", "xyz789"]
}
```

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `400 Bad Request` | Missing required fields | Provide both prompt and response |
| `422 Unprocessable Entity` | Invalid metadata format | Ensure metadata is valid JSON object |

---

## Memory Tools

### record_decision

Create a new decision, proposal, or constraint in semantic memory.

**Purpose**: Add new knowledge to the semantic memory system.

**Use Cases**:
- Recording architectural decisions
- Creating proposals for review
- Defining system constraints
- Documenting design choices

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "kind": {
      "type": "string",
      "enum": ["decision", "proposal", "constraint"],
      "default": "decision",
      "description": "Type of memory item"
    },
    "title": {
      "type": "string",
      "minLength": 3,
      "description": "Title of the decision"
    },
    "target": {
      "type": "string",
      "minLength": 1,
      "pattern": "^[a-z0-9_]+$",
      "description": "Target system or component"
    },
    "rationale": {
      "type": "string",
      "minLength": 10,
      "description": "Reasoning behind the decision"
    },
    "consequences": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Expected consequences or follow-up actions"
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "default": 0.8,
      "description": "Initial confidence score"
    },
    "phase": {
      "type": "string",
      "enum": ["pattern", "emergent", "canonical"],
      "default": "pattern",
      "description": "Decision lifecycle phase"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  },
  "required": ["title", "target", "rationale"]
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `kind` | string | `"decision"` | Type: `decision`, `proposal`, `constraint` |
| `title` | string | — | Decision title (required, min 3 chars) |
| `target` | string | — | Target component (required, lowercase alphanumeric) |
| `rationale` | string | — | Decision reasoning (required, min 10 chars) |
| `consequences` | array | `[]` | Expected consequences |
| `confidence` | number | `0.8` | Confidence (0.0-1.0) |
| `phase` | string | `"pattern"` | Lifecycle phase: `pattern`, `emergent`, `canonical` |
| `namespace` | string | `"default"` | Memory namespace |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Unique decision ID"
    },
    "status": {
      "type": "string",
      "enum": ["created", "conflict"]
    },
    "message": {
      "type": "string",
      "description": "Status message"
    },
    "conflicts": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "fid": {"type": "string"},
          "title": {"type": "string"},
          "similarity": {"type": "number"}
        }
      },
      "description": "Conflicting decisions (if any)"
    }
  }
}
```

**Example Usage**:

```python
# Record a decision
result = client.call_tool("record_decision", {
    "kind": "decision",
    "title": "Use PostgreSQL for production",
    "target": "database",
    "rationale": "PostgreSQL provides ACID compliance, proven reliability, and excellent performance for complex queries.",
    "consequences": [
        "Migrate from SQLite to PostgreSQL",
        "Set up connection pooling",
        "Update ORM configuration"
    ],
    "confidence": 0.9,
    "phase": "emergent",
    "namespace": "backend"
})

# Result:
{
  "fid": "abc123def456",
  "status": "created",
  "message": "Decision recorded successfully",
  "conflicts": []
}
```

**Conflict Handling**:

If a conflict is detected (similar decision exists), the response includes conflicting decisions:

```json
{
  "status": "conflict",
  "message": "Similar decision exists. Use supersede_decision to replace it.",
  "conflicts": [
    {
      "fid": "old_abc123",
      "title": "Use MySQL for production",
      "similarity": 0.75
    }
  ]
}
```

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `400 Bad Request` | Missing required fields | Provide title, target, and rationale |
| `422 Unprocessable Entity` | Validation failure | Check field lengths and formats |

---

### supersede_decision

Replace an existing decision with a new one. Used when a decision needs to be updated or corrected.

**Purpose**: Replace a decision while maintaining historical context.

**Use Cases**:
- Correcting a decision with new information
- Updating a decision based on lessons learned
- Replacing a deprecated choice

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Decision ID to supersede"
    },
    "title": {
      "type": "string",
      "minLength": 3,
      "description": "New title"
    },
    "target": {
      "type": "string",
      "minLength": 1,
      "pattern": "^[a-z0-9_]+$",
      "description": "Target component"
    },
    "rationale": {
      "type": "string",
      "minLength": 10,
      "description": "New rationale"
    },
    "consequences": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "New consequences"
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "default": 0.8,
      "description": "New confidence"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  },
  "required": ["fid", "title", "target", "rationale"]
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fid` | string | — | Decision ID to replace (required) |
| `title` | string | — | New title (required, min 3 chars) |
| `target` | string | — | Target (required, lowercase alphanumeric) |
| `rationale` | string | — | New rationale (required, min 10 chars) |
| `consequences` | array | `[]` | New consequences |
| `confidence` | number | `0.8` | New confidence (0.0-1.0) |
| `namespace` | string | `"default"` | Memory namespace |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "new_fid": {
      "type": "string",
      "description": "New decision ID"
    },
    "old_fid": {
      "type": "string",
      "description": "Old decision ID (now superseded)"
    },
    "status": {
      "type": "string",
      "enum": ["superseded"]
    },
    "message": {
      "type": "string",
      "description": "Status message"
    }
  }
}
```

**Example Usage**:

```python
# Supersede a decision
result = client.call_tool("supersede_decision", {
    "fid": "abc123def456",
    "title": "Use PostgreSQL 15+ with UUID primary keys",
    "target": "database",
    "rationale": "PostgreSQL 15 includes performance improvements. UUID keys avoid ID conflicts in multi-region deployment.",
    "consequences": [
        "Upgrade PostgreSQL to version 15",
        "Update schema to use UUID primary keys",
        "Update ORM mappings"
    ],
    "confidence": 0.95,
    "namespace": "backend"
})

# Result:
{
  "new_fid": "xyz789ghi012",
  "old_fid": "abc123def456",
  "status": "superseded",
  "message": "Decision superseded successfully"
}
```

**Behavior**:

1. Old decision is marked as `superseded`
2. New decision is created with status `active`
3. Old decision is renamed with `superseded_` prefix
4. Git commit is created with both changes

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `404 Not Found` | Decision not found | Verify the fid exists |
| `422 Unprocessable Entity` | Validation failure | Check field lengths and formats |

---

### accept_proposal

Promote a proposal to a decision, moving it from the proposal stage to active status.

**Purpose**: Accept a proposed change and make it an active decision.

**Use Cases**:
- Approving a design proposal
- Moving a draft decision to production
- Implementing a suggested change

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Proposal ID to accept"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  },
  "required": ["fid"]
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fid` | string | — | Proposal ID to accept (required) |
| `namespace` | string | `"default"` | Memory namespace |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Decision ID"
    },
    "status": {
      "type": "string",
      "enum": ["accepted"],
      "description": "New status"
    },
    "phase": {
      "type": "string",
      "enum": ["emergent", "canonical"],
      "description": "Updated phase"
    },
    "message": {
      "type": "string",
      "description": "Status message"
    }
  }
}
```

**Example Usage**:

```python
# Accept a proposal
result = client.call_tool("accept_proposal", {
    "fid": "prop_abc123",
    "namespace": "backend"
})

# Result:
{
  "fid": "abc123",
  "status": "active",
  "phase": "emergent",
  "message": "Proposal accepted and promoted to decision"
}
```

**Behavior**:

1. Proposal status changes from `draft` to `active`
2. Phase may advance from `pattern` to `emergent` or `canonical`
3. Git commit is created

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `404 Not Found` | Proposal not found | Verify the fid exists |
| `409 Conflict` | Not a proposal | fid is already a decision or constraint |

---

### reject_proposal

Mark a proposal as rejected, preventing it from being considered further.

**Purpose**: Reject a proposed change and document the rejection.

**Use Cases**:
- Declining a design proposal
- Archiving a draft that won't proceed
- Documenting a rejected alternative

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Proposal ID to reject"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  },
  "required": ["fid"]
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fid` | string | — | Proposal ID to reject (required) |
| `namespace` | string | `"default"` | Memory namespace |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Decision ID"
    },
    "status": {
      "type": "string",
      "enum": ["rejected"],
      "description": "New status"
    },
    "message": {
      "type": "string",
      "description": "Status message"
    }
  }
}
```

**Example Usage**:

```python
# Reject a proposal
result = client.call_tool("reject_proposal", {
    "fid": "prop_xyz789",
    "namespace": "backend"
})

# Result:
{
  "fid": "xyz789",
  "status": "rejected",
  "message": "Proposal rejected"
}
```

**Behavior**:

1. Proposal status changes to `rejected`
2. File is renamed with `rejected_` prefix
3. Git commit is created

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `404 Not Found` | Proposal not found | Verify the fid exists |
| `409 Conflict` | Not a proposal | fid is already a decision or constraint |

---

## Search Tools

### search_decisions

Search for relevant decisions using hybrid keyword and vector search.

**Purpose**: Find decisions, proposals, or constraints relevant to a query.

**Use Cases**:
- Finding past decisions on similar topics
- Discovering related architectural choices
- Checking for existing constraints

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "minLength": 1,
      "description": "Search query"
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 50,
      "default": 10,
      "description": "Maximum results"
    },
    "mode": {
      "type": "string",
      "enum": ["strict", "balanced", "fuzzy"],
      "default": "balanced",
      "description": "Search mode"
    },
    "kind": {
      "type": "string",
      "enum": ["decision", "proposal", "constraint", null],
      "default": null,
      "description": "Filter by kind"
    },
    "target": {
      "type": "string",
      "default": null,
      "description": "Filter by target"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  },
  "required": ["query"]
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | — | Search query (required) |
| `limit` | integer | `10` | Max results (1-50) |
| `mode` | string | `"balanced"` | Search mode: `strict`, `balanced`, `fuzzy` |
| `kind` | string | `null` | Filter by type (optional) |
| `target` | string | `null` | Filter by target (optional) |
| `namespace` | string | `"default"` | Memory namespace |

**Search Modes**:

| Mode | Behavior | Use Case |
|------|----------|----------|
| `strict` | High relevance threshold (0.8+) | Precise lookups, finding exact matches |
| `balanced` | Medium threshold (0.6+) | General search, balancing relevance and recall |
| `fuzzy` | Low threshold (0.4+) | Discovery, finding related concepts |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "results": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "fid": {"type": "string"},
          "title": {"type": "string"},
          "target": {"type": "string"},
          "kind": {"type": "string"},
          "status": {"type": "string"},
          "phase": {"type": "string"},
          "confidence": {"type": "number"},
          "score": {"type": "number"},
          "rationale": {"type": "string"},
          "created_at": {"type": "string", "format": "date-time"},
          "updated_at": {"type": "string", "format": "date-time"}
        }
      }
    },
    "total": {
      "type": "integer",
      "description": "Total matching results"
    }
  }
}
```

**Example Usage**:

```python
# Search for database decisions
result = client.call_tool("search_decisions", {
    "query": "database migration strategy",
    "limit": 5,
    "mode": "balanced",
    "target": "database",
    "namespace": "backend"
})

# Result:
{
  "results": [
    {
      "fid": "abc123",
      "title": "Use exponential backoff for database retries",
      "target": "database",
      "kind": "decision",
      "status": "active",
      "phase": "canonical",
      "confidence": 0.95,
      "score": 0.87,
      "rationale": "Prevents overwhelming server during outages.",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-20T14:45:00Z"
    }
    // ... more results
  ],
  "total": 5
}
```

**Performance**:

- **Mobile (GGUF)**: ~2,650 ops/sec
- **Server (MiniLM)**: ~3,402 ops/sec
- **Search Mode Impact**: Balanced mode is default and most performant

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `400 Bad Request` | Empty query | Provide non-empty query string |
| `422 Unprocessable Entity` | Invalid filter | Check kind and target values |

---

### get_decisions

Retrieve decisions by filters (ID, status, kind, target, namespace).

**Purpose**: Get decisions matching specific criteria.

**Use Cases**:
- Retrieving all active decisions
- Finding decisions for a specific target
- Getting decisions by status or kind

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Specific decision ID"
    },
    "status": {
      "type": "string",
      "enum": ["active", "superseded", "deprecated", "rejected", "draft"],
      "description": "Filter by status"
    },
    "kind": {
      "type": "string",
      "enum": ["decision", "proposal", "constraint"],
      "description": "Filter by kind"
    },
    "target": {
      "type": "string",
      "description": "Filter by target"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100,
      "default": 20,
      "description": "Maximum results"
    }
  }
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fid` | string | `null` | Specific decision ID (optional) |
| `status` | string | `null` | Filter by status (optional) |
| `kind` | string | `null` | Filter by kind (optional) |
| `target` | string | `null` | Filter by target (optional) |
| `namespace` | string | `"default"` | Memory namespace |
| `limit` | integer | `20` | Max results (1-100) |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "decisions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "fid": {"type": "string"},
          "title": {"type": "string"},
          "target": {"type": "string"},
          "kind": {"type": "string"},
          "status": {"type": "string"},
          "phase": {"type": "string"},
          "confidence": {"type": "number"},
          "rationale": {"type": "string"},
          "created_at": {"type": "string", "format": "date-time"},
          "updated_at": {"type": "string", "format": "date-time"}
        }
      }
    },
    "total": {
      "type": "integer"
    }
  }
}
```

**Example Usage**:

```python
# Get all active decisions for database target
result = client.call_tool("get_decisions", {
    "status": "active",
    "target": "database",
    "namespace": "backend",
    "limit": 10
})

# Result:
{
  "decisions": [
    {
      "fid": "abc123",
      "title": "Use PostgreSQL for production",
      "target": "database",
      "kind": "decision",
      "status": "active",
      "phase": "canonical",
      "confidence": 0.95,
      "rationale": "ACID compliance and proven reliability",
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-20T14:45:00Z"
    }
    // ... more decisions
  ],
  "total": 3
}
```

**Performance**:

- ID lookup: ~4,800 ops/sec (keyword search)
- Filtered queries: ~1,200 ops/sec (SQLite query)

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `404 Not Found` | Decision ID not found | Verify fid exists |
| `422 Unprocessable Entity` | Invalid filter | Check filter values |

---

### get_decision_history

Get the complete evolution of a decision, including all superseded versions.

**Purpose**: Track decision evolution and understand context changes.

**Use Cases**:
- Understanding why a decision was made
- Learning from past changes
- Auditing decision history

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Decision ID"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  },
  "required": ["fid"]
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fid` | string | — | Decision ID (required) |
| `namespace` | string | `"default"` | Memory namespace |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "current": {
      "type": "object",
      "description": "Current decision"
    },
    "history": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "fid": {"type": "string"},
          "title": {"type": "string"},
          "target": {"type": "string"},
          "rationale": {"type": "string"},
          "superseded_at": {"type": "string", "format": "date-time"},
          "superseded_by": {"type": "string"}
        }
      },
      "description": "Previous versions"
    }
  }
}
```

**Example Usage**:

```python
# Get decision history
result = client.call_tool("get_decision_history", {
    "fid": "abc123",
    "namespace": "backend"
})

# Result:
{
  "current": {
    "fid": "abc123",
    "title": "Use PostgreSQL 15+ with UUID keys",
    "target": "database",
    "rationale": "PostgreSQL 15 includes performance improvements...",
    "status": "active",
    "phase": "canonical"
  },
  "history": [
    {
      "fid": "old_xyz789",
      "title": "Use PostgreSQL for production",
      "target": "database",
      "rationale": "ACID compliance and proven reliability",
      "superseded_at": "2024-01-20T14:45:00Z",
      "superseded_by": "abc123"
    }
  ]
}
```

**Behavior**:

1. Returns current decision
2. Lists all previous versions in chronological order
3. Includes when and why each version was superseded

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `404 Not Found` | Decision not found | Verify fid exists |

---

### get_recent_events

Retrieve recent episodic events from memory.

**Purpose**: Get recent activity history for monitoring or context.

**Use Cases**:
- Monitoring recent activity
- Understanding recent interactions
- Debugging behavior

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100,
      "default": 20,
      "description": "Maximum events to return"
    },
    "kind": {
      "type": "string",
      "enum": ["tool_call", "agent_action", "observation", "error", "user_action", "system_event", "decision_change", "proposal_change", "constraint_change", "goal_state", "confidence_update", "evidence_link", "system_message", "procedural_generated", null],
      "default": null,
      "description": "Filter by event kind"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  }
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | `20` | Max events (1-100) |
| `kind` | string | `null` | Filter by event kind (optional) |
| `namespace` | string | `"default"` | Memory namespace |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "events": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": {"type": "string"},
          "kind": {"type": "string"},
          "description": {"type": "string"},
          "timestamp": {"type": "string", "format": "date-time"},
          "namespace": {"type": "string"},
          "metadata": {"type": "object"},
          "linked_ids": {
            "type": "array",
            "items": {"type": "string"}
          }
        }
      }
    },
    "total": {
      "type": "integer"
    }
  }
}
```

**Example Usage**:

```python
# Get recent events
result = client.call_tool("get_recent_events", {
    "limit": 10,
    "namespace": "backend"
})

# Result:
{
  "events": [
    {
      "id": "evt_abc123",
      "kind": "tool_call",
      "description": "Called http_client.get",
      "timestamp": "2024-01-20T15:30:00Z",
      "namespace": "backend",
      "metadata": {
        "tool": "http_client",
        "endpoint": "/api/3.1.2/health",
        "duration_ms": 1200
      },
      "linked_ids": []
    }
    // ... more events
  ],
  "total": 10
}
```

**Performance**:

- ~4,800 ops/sec (keyword search)
- Pagination supported via limit parameter

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `422 Unprocessable Entity` | Invalid kind | Check event kind value |

---

## Evidence Tools

### link_evidence

Link episodic events as evidence to semantic decisions.

**Purpose**: Connect events (actions, observations, errors) to decisions for traceability.

**Use Cases**:
- Providing evidence for why a decision was made
- Documenting real-world outcomes
- Building decision audit trail

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "event_id": {
      "type": "string",
      "description": "Event ID to link"
    },
    "decision_ids": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "minItems": 1,
      "maxItems": 10,
      "description": "Decision IDs to link to"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  },
  "required": ["event_id", "decision_ids"]
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event_id` | string | — | Event ID to link (required) |
| `decision_ids` | array | — | Decision IDs to link (1-10, required) |
| `namespace` | string | `"default"` | Memory namespace |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "event_id": {
      "type": "string",
      "description": "Event ID"
    },
    "linked_decisions": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Decision IDs that were linked"
    },
    "total_links": {
      "type": "integer",
      "description": "Total number of links created"
    }
  }
}
```

**Example Usage**:

```python
# Link evidence
result = client.call_tool("link_evidence", {
    "event_id": "evt_abc123",
    "decision_ids": ["decision_xyz", "decision_def"],
    "namespace": "backend"
})

# Result:
{
  "event_id": "evt_abc123",
  "linked_decisions": ["decision_xyz", "decision_def"],
  "total_links": 2
}
```

**Impact**:

- Linked decisions receive +20% confidence boost per link
- Creates traceable audit trail
- Improves search relevance

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `400 Bad Request` | Missing IDs | Provide both event_id and decision_ids |
| `404 Not Found` | Event or decision not found | Verify IDs exist |
| `409 Conflict` | Already linked | Evidence already linked to decision |

---

## Memory Tools (Continued)

### update_decision

Update metadata for a decision (confidence, status, phase, etc.).

**Purpose**: Modify decision properties without creating a new version.

**Use Cases**:
- Adjusting confidence based on new evidence
- Changing decision status
- Updating lifecycle phase

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Decision ID to update"
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "New confidence score"
    },
    "status": {
      "type": "string",
      "enum": ["active", "superseded", "deprecated", "rejected", "draft"],
      "description": "New status"
    },
    "phase": {
      "type": "string",
      "enum": ["pattern", "emergent", "canonical"],
      "description": "New phase"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  },
  "required": ["fid"]
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fid` | string | — | Decision ID to update (required) |
| `confidence` | number | `null` | New confidence (0.0-1.0, optional) |
| `status` | string | `null` | New status (optional) |
| `phase` | string | `null` | New phase (optional) |
| `namespace` | string | `"default"` | Memory namespace |

**At least one of `confidence`, `status`, or `phase` must be provided.**

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Decision ID"
    },
    "updated_fields": {
      "type": "array",
      "items": {
        "type": "string"
      },
      "description": "Fields that were updated"
    },
    "message": {
      "type": "string",
      "description": "Status message"
    }
  }
}
```

**Example Usage**:

```python
# Update decision confidence
result = client.call_tool("update_decision", {
    "fid": "abc123",
    "confidence": 0.95,
    "namespace": "backend"
})

# Result:
{
  "fid": "abc123",
  "updated_fields": ["confidence"],
  "message": "Decision updated successfully"
}
```

**Behavior**:

- Only specified fields are updated
- Other fields remain unchanged
- Git commit is created for audit trail

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `400 Bad Request` | No fields to update | Provide at least one of confidence, status, or phase |
| `404 Not Found` | Decision not found | Verify fid exists |
| `422 Unprocessable Entity` | Invalid values | Check field values and constraints |

---

### sync_git

Sync semantic memory changes to Git repository.

**Purpose**: Commit pending semantic memory changes to Git.

**Use Cases**:
- Forcing immediate sync to remote repository
- Creating checkpoint commits
- Auditing changes

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  }
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `namespace` | string | `"default"` | Memory namespace |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "commit_hash": {
      "type": "string",
      "description": "Git commit hash"
    },
    "files_committed": {
      "type": "integer",
      "description": "Number of files committed"
    },
    "message": {
      "type": "string",
      "description": "Commit message"
    }
  }
}
```

**Example Usage**:

```python
# Sync to Git
result = client.call_tool("sync_git", {
    "namespace": "backend"
})

# Result:
{
  "commit_hash": "abc123def456",
  "files_committed": 3,
  "message": "Sync semantic memory: 3 decisions"
}
```

**Behavior**:

1. Stages all modified semantic memory files
2. Creates Git commit with descriptive message
3. Returns commit hash for reference

**Note**: Most write operations automatically sync to Git. This tool is for manual sync or forcing immediate commit.

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `500 Internal Server Error` | Git operation failed | Check Git configuration and repository health |

---

### forget

Delete memories (decisions, proposals, constraints) from semantic memory.

**Purpose**: Remove memories permanently from semantic memory.

**Use Cases**:
- Cleaning up test data
- Removing deprecated decisions
- Forgetting incorrect information

**Request Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Decision ID to forget"
    },
    "namespace": {
      "type": "string",
      "default": "default",
      "description": "Memory namespace"
    }
  },
  "required": ["fid"]
}
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fid` | string | — | Decision ID to forget (required) |
| `namespace` | string | `"default"` | Memory namespace |

**Response Schema**:

```json
{
  "type": "object",
  "properties": {
    "fid": {
      "type": "string",
      "description": "Decision ID that was forgotten"
    },
    "status": {
      "type": "string",
      "enum": ["forgotten"],
      "description": "Operation status"
    },
    "message": {
      "type": "string",
      "description": "Status message"
    }
  }
}
```

**Example Usage**:

```python
# Forget a decision
result = client.call_tool("forget", {
    "fid": "abc123",
    "namespace": "backend"
})

# Result:
{
  "fid": "abc123",
  "status": "forgotten",
  "message": "Decision forgotten successfully"
}
```

**Behavior**:

1. Removes decision from semantic memory
2. Deletes Markdown file
3. Removes from SQLite metadata index
4. Removes from vector index
5. Git commit is created with deletion

**Warning**: This operation is irreversible. Use with caution.

**Error Handling**:

| Error | Cause | Resolution |
|-------|-------|------------|
| `404 Not Found` | Decision not found | Verify fid exists |
| `403 Forbidden` | Trust boundary violation | Decision is HUMAN_ONLY and current role lacks permission |

---

## Common Response Patterns

### Success Response

Most tools return success responses in this format:

```json
{
  "status": "success",
  "message": "Operation completed successfully",
  "data": { /* tool-specific data */ }
}
```

### Error Response

Errors follow this format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": { /* additional context */ }
  }
}
```

### Pagination

For tools that return multiple results:

```json
{
  "results": [ /* array of items */ ],
  "total": 100,
  "limit": 20,
  "offset": 0
}
```

---

## Performance Benchmarks

### Tool Throughput

| Tool | Mobile (GGUF) | Server (MiniLM) |
|------|---------------|----------------|
| `search_decisions` | 2,650 ops/sec | 3,402 ops/sec |
| `get_decisions` | 4,800 ops/sec | 16,200 ops/sec |
| `get_recent_events` | 4,800 ops/sec | 16,200 ops/sec |
| `record_decision` | 7.0 ops/sec | 70.6 ops/sec |
| `supersede_decision` | 7.0 ops/sec | 70.6 ops/sec |
| `link_evidence` | 15.0 ops/sec | 150.0 ops/sec |

### Latency

| Tool | Mobile (GGUF) | Server (MiniLM) |
|------|---------------|----------------|
| `search_decisions` | 0.13 ms | 0.05 ms |
| `get_decisions` | 0.05 ms | 0.02 ms |
| `record_decision` | 142.7 ms | 14.1 ms |
| `link_evidence` | 66.7 ms | 6.7 ms |

---

## Role-Based Access Control

### Permissions by Role

| Tool | ADMIN | USER | GUEST |
|------|-------|------|-------|
| `record_decision` | ✓ | ✓ | ✗ |
| `supersede_decision` | ✓ | ✗ | ✗ |
| `accept_proposal` | ✓ | ✗ | ✗ |
| `reject_proposal` | ✓ | ✗ | ✗ |
| `update_decision` | ✓ | ✗ | ✗ |
| `forget` | ✓ | ✗ | ✗ |
| `sync_git` | ✓ | ✗ | ✗ |
| `search_decisions` | ✓ | ✓ | ✓ |
| `get_decisions` | ✓ | ✓ | ✓ |
| `get_decision_history` | ✓ | ✓ | ✓ |
| `get_recent_events` | ✓ | ✓ | ✓ |
| `link_evidence` | ✓ | ✓ | ✗ |
| `bridge-context` | ✓ | ✓ | ✓ |
| `bridge-record` | ✓ | ✓ | ✗ |

### Setting Default Role

```bash
# Server startup
ledgermind run --default-role ADMIN

# Via configuration
export LEDGERMIND_DEFAULT_ROLE=ADMIN
```

---

## Best Practices

### Tool Selection

| Scenario | Recommended Tool |
|----------|----------------|
| Get context for LLM prompt | `bridge-context` |
| Record AI response | `bridge-record` |
| New architectural decision | `record_decision` (kind=decision) |
| Suggest improvement | `record_decision` (kind=proposal) |
| Update existing decision | `supersede_decision` |
| Find past decisions | `search_decisions` |
| Get decision evolution | `get_decision_history` |
| Add evidence to decision | `link_evidence` |
| Adjust confidence | `update_decision` |
| Manual Git sync | `sync_git` |
| Delete wrong decision | `forget` |

### Error Handling Strategy

```python
# Retry with exponential backoff
def robust_tool_call(tool_name, params, max_retries=3):
    for attempt in range(max_retries):
        try:
            result = client.call_tool(tool_name, params)
            return result
        except TemporaryFailure as e:
            delay = 2 ** attempt
            time.sleep(delay)
    raise MaxRetriesExceeded(f"Failed after {max_retries} retries")
```

### Batch Operations

```python
# Link multiple evidence items efficiently
for decision_id in decision_ids:
    client.call_tool("link_evidence", {
        "event_id": event_id,
        "decision_ids": [decision_id]
    })
```

---

## Next Steps

For integration details:
- [Integration Guide](integration-guide.md) — Client integration patterns
- [Configuration](configuration.md) — Role and capability configuration

For API reference:
- [API Reference](api-reference.md) — Python API signatures
- [Data Schemas](data-schemas.md) — Complete model definitions

For architectural context:
- [Architecture](architecture.md) — System internals and data flow

---

