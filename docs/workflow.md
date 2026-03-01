# Workflows

Common operational patterns and workflows for using LedgerMind effectively.

---

## Introduction

This document covers practical workflows for common scenarios when using LedgerMind. Each workflow includes:

- **Use Case**: When and why to use this workflow
- **Prerequisites**: What you need before starting
- **Steps**: Detailed step-by-step instructions
- **Code Examples**: Python code for implementation
- **Best Practices**: Tips for getting the most out of the workflow

**Audience**:
- **Developers** integrating memory management into daily workflows
- **DevOps Engineers** automating operational tasks
- **Software Architects** maintaining decision history

**Workflow Categories**:

| Category | Workflows | Complexity |
|----------|-----------|------------|
| **Getting Started** | First Run, First Decision | Beginner |
| **Daily Development** | Context Injection, Recording, Searching | Intermediate |
| **Team Collaboration** | Multi-Agent, Code Review, Knowledge Sharing | Advanced |
| **Maintenance** | Decay Management, Git Sync, Memory Cleanup | Intermediate |
| **Integration** | MCP Server, VS Code Extension, CLI Hooks | Advanced |

---

## Getting Started Workflows

### Workflow: First Run Setup

**Purpose**: Set up LedgerMind for the first time and verify it's working.

**Use Case**: You've just installed LedgerMind and want to get started.

**Prerequisites**:
- Python 3.11+ installed
- Git installed and configured

**Steps**:

1. **Install LedgerMind**
   ```bash
   pip install ledgermind
   ```

2. **Initialize LedgerMind**
   ```bash
   ledgermind init
   ```

3. **Follow Interactive Prompts**:
   - Path: `~/.ledgermind` (default)
   - Namespace: `default` (can change later)
   - Vector Model: `jina-v5-4bit` (recommended for mobile)
   - TTL: `30` days (default)
   - Arbitration Mode: `lite` (algorithmic, fastest)

4. **Verify Setup**
   ```bash
   # Check memory directory
   ls -la ~/.ledgermind

   # Expected output:
   # semantic/
   # episodic.db
   # vector_index.npz
   # config.json
   # audit.log
   ```

5. **Start MCP Server**
   ```bash
   ledgermind run --path ~/.ledgermind
   ```

6. **Test Connection**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(
       memory_path="~/.ledgermind"
   )

   # Record first decision
   bridge.record_decision(
       title="Setup LedgerMind",
       target="development",
       rationale="Autonomous memory management for better decisions.",
       confidence=1.0
   )

   print("✓ LedgerMind is working!")
   ```

**Best Practices**:
- Use default settings for initial setup
- Verify Git is configured before recording decisions
- Start with `lite` arbitration mode for fastest performance
- Test with a simple decision before complex workflows

---

### Workflow: Recording Your First Decision

**Purpose**: Create your first semantic memory entry.

**Use Case**: You want to start tracking architectural decisions.

**Prerequisites**:
- LedgerMind initialized
- MCP server running

**Steps**:

1. **Identify the Decision**
   - What did you decide? (title)
   - What component does it affect? (target)
   - Why did you decide it? (rationale)
   - What are the consequences? (consequences)

2. **Record via Python**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   bridge.record_decision(
       kind="decision",
       title="Use PostgreSQL for production database",
       target="database",
       rationale=(
           "PostgreSQL provides ACID compliance, proven reliability, "
           "and excellent performance for complex queries. "
           "It also supports advanced features like JSON columns and "
           "full-text search."
       ),
       consequences=[
           "Migrate from SQLite to PostgreSQL",
           "Set up connection pooling with pgbouncer",
           "Configure automated backups",
           "Update ORM mappings"
       ],
       confidence=0.9,
       phase="emergent"
   )

   print(f"✓ Decision recorded: {bridge._memory.semantic_store.last_fid}")
   ```

3. **Verify Recording**
   ```python
   # Search for the decision
   results = bridge.search_decisions("PostgreSQL", limit=1)

   if results:
       print(f"✓ Found: {results[0]['title']}")
       print(f"  Score: {results[0]['score']:.2f}")
       print(f"  Confidence: {results[0]['confidence']:.2f}")
   ```

**Best Practices**:
- Write clear, specific titles
- Include thorough rationale (10+ words required)
- List concrete consequences for future reference
- Start with lower confidence if uncertain (0.6-0.7)

---

## Daily Development Workflows

### Workflow: Context Injection Before Coding

**Purpose**: Retrieve relevant past decisions before starting a task.

**Use Case**: You're about to implement a feature and want to know past decisions.

**Prerequisites**:
- LedgerMind initialized
- Past decisions recorded

**Steps**:

1. **Get Context for Your Task**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   # Get context for API development
   context = bridge.get_context_for_prompt(
       "Implement user authentication endpoint",
       limit=3
   )

   print(context)
   ```

2. **Review Retrieved Context**
   ```json
   {
     "source": "ledgermind",
     "memories": [
       {
         "id": "abc123",
         "title": "Use JWT tokens for authentication",
         "target": "auth",
         "score": 0.92,
         "status": "active",
         "kind": "decision",
         "rationale": "JWT is stateless and scales well...",
         "procedural_guide": [
           "1. Generate tokens with 15-minute expiration",
           "2. Include user ID in payload",
           "3. Sign with HS256 algorithm"
         ]
       },
       // ... more memories
     ]
   }
   ```

3. **Use Context in Your Work**
   - Read through retrieved decisions
   - Follow procedural guides if available
   - Check for conflicts with new approach

4. **Update if Needed**
   ```python
   # If you find a better approach, supersede the old decision
   bridge.supersede_decision(
       fid="abc123",
       title="Use JWT with refresh tokens",
       target="auth",
       rationale="Refresh tokens improve security by...",
       confidence=0.95
   )
   ```

**Best Practices**:
- Always check context before major implementations
- Use `limit=3-5` to avoid overwhelming context
- Review procedural guides for implementation steps
- Supersede decisions rather than forgetting them

---

### Workflow: Recording After Coding

**Purpose**: Record decisions and interactions after completing work.

**Use Case**: You've implemented a feature and want to document what you did.

**Prerequisites**:
- LedgerMind initialized
- Code implemented

**Steps**:

1. **Record the Decision**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   # Record architectural decision
   bridge.record_decision(
       kind="decision",
       title="Use exponential backoff for API retries",
       target="api_client",
       rationale=(
           "Exponential backoff prevents overwhelming the server "
           "during outages. Start with 1s delay, double each retry, "
           "cap at 10s maximum."
       ),
       consequences=[
           "Implement jitter to avoid thundering herd",
           "Add circuit breaker after 5 consecutive failures",
           "Log retry attempts with exponential delay"
       ],
       confidence=0.85
   )
   ```

2. **Record the Implementation**
   ```python
   # Record what was done
   bridge.record_interaction(
       prompt="Implement exponential backoff",
       response="Implemented retry logic with exponential backoff (1s, 2s, 4s, 8s, 10s max)",
       success=True,
       metadata={
           "tool_used": "python",
           "file": "api_client.py",
           "lines_modified": 45,
           "duration_seconds": 180
       }
   )
   ```

3. **Link Evidence**
   ```python
   # Link implementation events to decision
   # (Automatically done by record_interaction)
   # Or manually link specific events
   event_id = "evt_abc123"  # From record_interaction
   decision_id = bridge._memory.semantic_store.last_fid

   bridge.link_evidence(
       event_id=event_id,
       decision_id=decision_id
   )
   ```

**Best Practices**:
- Record both the decision (why) and implementation (what)
- Include metadata for traceability (files, time, duration)
- Link evidence to show real-world outcomes
- Use `confidence` to reflect uncertainty

---

### Workflow: Searching for Related Work

**Purpose**: Find past decisions related to your current task.

**Use Case**: You're working on a feature and want to know if it was decided before.

**Prerequisites**:
- LedgerMind initialized
- Past decisions recorded

**Steps**:

1. **Search by Keyword**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   # Search for database decisions
   results = bridge.search_decisions(
       "database migration",
       limit=5,
       mode="balanced"
   )

   for result in results:
       print(f"{result['score']:.2f} - {result['title']}")
       print(f"  Target: {result['target']}")
       print(f"  Phase: {result['phase']}")
       print(f"  Confidence: {result['confidence']:.2f}")
       print()
   ```

2. **Filter by Target**
   ```python
   # Get all decisions for a specific component
   results = bridge.get_decisions(
       target="database",
       status="active",
       limit=10
   )

   for result in results:
       print(f"{result['title']}")
       print(f"  Rationale: {result['rationale']}")
   ```

3. **View Decision History**
   ```python
   # See how a decision evolved
   history = bridge.get_decision_history(fid="abc123")

   print(f"Current: {history['current']['title']}")
   print()

   print("History:")
   for old in history['history']:
       print(f"  - {old['title']}")
       print(f"    Superseded: {old['superseded_at']}")
       print(f"    By: {old['superseded_by']}")
   ```

**Best Practices**:
- Use descriptive search queries
- Filter by target to narrow results
- Check decision history to understand evolution
- Note confidence scores (higher = more certain)

---

## Team Collaboration Workflows

### Workflow: Multi-Agent Memory Isolation

**Purpose**: Separate memories for different agents or teams.

**Use Case**: Multiple AI agents or teams work on the same codebase.

**Prerequisites**:
- LedgerMind initialized
- Multiple agents/teams

**Steps**:

1. **Configure Namespaces**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   # Agent A: Frontend
   frontend_bridge = IntegrationBridge(
       memory_path="~/.ledgermind",
       namespace="frontend"
   )

   # Agent B: Backend
   backend_bridge = IntegrationBridge(
       memory_path="~/.ledgermind",
       namespace="backend"
   )

   # Agent C: DevOps
   devops_bridge = IntegrationBridge(
       memory_path="~/.ledgermind",
       namespace="devops"
   )
   ```

2. **Record Decisions in Isolation**
   ```python
   # Frontend records UI decision
   frontend_bridge.record_decision(
       title="Use React for frontend",
       target="ui",
       rationale="Component-based architecture improves...",
       namespace="frontend"
   )

   # Backend records API decision
   backend_bridge.record_decision(
       title="Use REST API",
       target="api",
       rationale="REST is widely supported and...",
       namespace="backend"
   )
   ```

3. **Search Within Namespace**
   ```python
   # Frontend only sees frontend decisions
   ui_decisions = frontend_bridge.search_decisions("button styling")

   # Backend only sees backend decisions
   api_decisions = backend_bridge.search_decisions("authentication")
   ```

**Best Practices**:
- Use descriptive namespace names (frontend, backend, api, ui)
- Keep memory path shared to reduce storage
- Document namespace conventions in team docs
- Use namespaces for logical separation, not security

---

### Workflow: Code Review with Memory

**Purpose**: Use past decisions to inform code reviews.

**Use Case**: Reviewing pull requests and checking against decisions.

**Prerequisites**:
- LedgerMind initialized
- Past decisions recorded
- Pull request to review

**Steps**:

1. **Identify Changed Components**
   ```bash
   # See what changed in the PR
   git diff main...pr-branch --stat

   # Example output:
   # api/user_service.py       | 45 +++++
   # database/migrations/001.sql | 12 ++
   ```

2. **Get Relevant Decisions**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   # Get decisions for changed components
   api_decisions = bridge.get_decisions(target="api")
   db_decisions = bridge.get_decisions(target="database")

   print(f"Found {len(api_decisions)} API decisions")
   print(f"Found {len(db_decisions)} database decisions")
   ```

3. **Compare Against Code**
   ```python
   # Check if code follows decisions
   api_decisions = bridge.get_decisions(target="api", status="active")

   for decision in api_decisions:
       print(f"\n{decision['title']}")
       print(f"  Rationale: {decision['rationale']}")

       # Check if code aligns
       if "authentication" in decision['title'].lower():
           # Verify authentication is implemented
           # (manual code review here)
           pass
   ```

4. **Record Review Decision**
   ```python
   # Record review outcome
   bridge.record_decision(
       kind="decision",
       title="Approve PR #123 with authentication fix",
       target="code_review",
       rationale=(
           "Code follows existing authentication decisions. "
           "Added JWT tokens as per decision abc123."
       ),
       confidence=0.9
   )
   ```

**Best Practices**:
- Check decisions for all changed components
- Document why code does/doesn't follow decisions
- Record review outcomes for future reference
- Link PR evidence to relevant decisions

---

### Workflow: Knowledge Sharing Across Teams

**Purpose**: Share decisions between teams while maintaining namespaces.

**Use Case**: Teams need to share some decisions while keeping others private.

**Prerequisites**:
- Multiple namespaces configured
- Shared Git repository

**Steps**:

1. **Record Team-Specific Decisions**
   ```python
   # Frontend team records UI decision
   frontend_bridge = IntegrationBridge(
       memory_path="~/.ledgermind",
       namespace="frontend"
   )

   frontend_bridge.record_decision(
       title="Use Material-UI components",
       target="ui_library",
       rationale="Material-UI provides consistent design...",
   )

   # This decision is only in "frontend" namespace
   ```

2. **Record Shared Decisions**
   ```python
   # Shared team records architecture decision
   shared_bridge = IntegrationBridge(
       memory_path="~/.ledgermind",
       namespace="shared"
   )

   shared_bridge.record_decision(
       title="Use microservices architecture",
       target="architecture",
       rationale="Microservices allow independent scaling...",
   )

   # This decision is accessible to all teams
   ```

3. **Sync to Shared Git**
   ```python
   # All teams sync to shared repository
   frontend_bridge.sync_git()
   backend_bridge.sync_git()
   devops_bridge.sync_git()
   shared_bridge.sync_git()
   ```

4. **Access Shared Decisions**
   ```python
   # Any team can access shared namespace
   backend_bridge = IntegrationBridge(
       memory_path="~/.ledgermind",
       namespace="backend"
   )

   # Search across all namespaces (if configured)
   # Or access shared decisions directly
   # (Implementation depends on access control)
   ```

**Best Practices**:
- Use "shared" namespace for cross-team decisions
- Document which decisions are shared
- Keep team-specific decisions in private namespaces
- Sync all namespaces to shared Git repository

---

## Maintenance Workflows

### Workflow: Memory Decay Management

**Purpose**: Manage memory lifecycle and clean up old data.

**Use Case**: Memory has grown large and you want to clean up old decisions.

**Prerequisites**:
- LedgerMind initialized
- Memory with old decisions

**Steps**:

1. **Check Memory Statistics**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   stats = bridge.get_stats()
   print(f"Episodic events: {stats['episodic_count']}")
   print(f"Semantic decisions: {stats['semantic_count']}")
   print(f"Vector embeddings: {stats['vector_count']}")
   ```

2. **Run Decay Engine**
   ```python
   # Run decay process (archives old events, decays low-confidence decisions)
   result = bridge.run_decay()

   print(f"Archived events: {result['archived_count']}")
   print(f"Decayed decisions: {result['decayed_count']}")
   print(f"Fogotten decisions: {result['forgotten_count']}")
   ```

3. **Review Decayed Decisions**
   ```python
   # Find decisions with low confidence
   results = bridge.search_decisions(
       "",
       limit=50,
       mode="fuzzy"
   )

   for result in results:
       if result['confidence'] < 0.3:
           print(f"{result['title']} (confidence: {result['confidence']:.2f})")
   ```

4. **Adjust TTL if Needed**
   ```python
   # Reinitialize with different TTL
   # (Requires stopping and restarting)
   # Current TTL configuration in: ~/.ledgermind/config.json
   ```

**Best Practices**:
- Run decay periodically (weekly/monthly)
- Review low-confidence decisions before forgetting
- Use appropriate TTL for your use case (7-90 days)
- Monitor memory statistics over time

---

### Workflow: Git Sync and Audit

**Purpose**: Maintain Git audit trail and sync to remote repository.

**Use Case**: You want to maintain history of all decision changes.

**Prerequisites**:
- LedgerMind initialized
- Git repository configured

**Steps**:

1. **Check Git Status**
   ```bash
   cd ~/.ledgermind
   git status
   ```

2. **Manual Sync**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   # Force sync to Git
   result = bridge.sync_git()

   print(f"Commit: {result['commit_hash']}")
   print(f"Files: {result['files_committed']}")
   ```

3. **Review Git History**
   ```bash
   # View recent commits
   cd ~/.ledgermind
   git log --oneline -10

   # View specific decision history
   git log --all --source --full-history -- semantic/abc123.md

   # See what changed in a commit
   git show abc123def456
   ```

4. **Push to Remote**
   ```bash
   # Push to remote repository
   cd ~/.ledgermind
   git push origin main

   # Or push automatically via MCP server
   # (Configure in MCP server startup)
   ```

**Best Practices**:
- Sync to Git after critical decisions
- Review Git history for decision evolution
- Push to remote repository for team access
- Use Git tags for important milestones

---

### Workflow: Memory Cleanup

**Purpose**: Remove obsolete or incorrect decisions.

**Use Case**: Decisions are outdated or no longer relevant.

**Prerequisites**:
- LedgerMind initialized
- Decisions to remove identified

**Steps**:

1. **Identify Decisions to Remove**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   # Find deprecated decisions
   results = bridge.get_decisions(status="deprecated")

   for result in results:
       print(f"{result['fid']}: {result['title']}")
   ```

2. **Review Before Forgetting**
   ```python
   # Get decision history before deleting
   fid = "abc123"
   history = bridge.get_decision_history(fid=fid)

   print(f"Current: {history['current']['title']}")
   print(f"History: {len(history['history'])} versions")
   ```

3. **Forget Decision**
   ```python
   # Permanently remove decision
   bridge.forget(fid="abc123")

   print(f"✓ Forgotten decision: {fid}")
   ```

4. **Verify Removal**
   ```python
   # Check decision is gone
   try:
       result = bridge.get_decisions(fid="abc123")
       print("Decision still exists (unexpected)")
   except Exception:
       print("✓ Decision successfully forgotten")
   ```

**Best Practices**:
- Always review before forgetting
- Supersede decisions instead of forgetting when possible
- Check decision history before removal
- Forget only truly obsolete or incorrect decisions

---

## Integration Workflows

### Workflow: MCP Server Integration

**Purpose**: Use LedgerMind as an MCP server for IDE integration.

**Use Case**: You want Claude Desktop or Cursor IDE to use LedgerMind.

**Prerequisites**:
- LedgerMind installed
- MCP-compatible client (Claude Desktop, Cursor)

**Steps**:

1. **Start MCP Server**
   ```bash
   # Start LedgerMind as MCP server
   ledgermind run --path ~/.ledgermind --metrics-port 9090
   ```

2. **Configure Client**

   **Claude Desktop**:
   ```json
   // ~/.claude/config.json
   {
     "mcpServers": [
       {
         "command": "ledgermind",
         "args": ["run", "--path", "/absolute/path/to/.ledgermind"]
       }
     ]
   }
   ```

   **Cursor IDE**:
   ```json
   // Cursor Settings → MCP Servers
   {
     "servers": [
       {
         "name": "ledgermind",
         "command": "ledgermind",
         "args": ["run", "--path", "/absolute/path/to/.ledgermind"]
       }
     ]
   }
   ```

3. **Verify Connection**
   ```python
   # Test connection from client
   # (Client-specific, depends on MCP client)
   ```

4. **Use MCP Tools**
   ```python
   # Example via Claude Desktop
   # Claude will automatically call LedgerMind tools
   # You don't need to write code
   ```

**Best Practices**:
- Use absolute paths for memory directory
- Configure API key for production deployments
- Monitor server logs for errors
- Set appropriate role permissions

---

### Workflow: VS Code Extension Setup

**Purpose**: Integrate LedgerMind into VS Code development workflow.

**Use Case**: You want automatic memory injection during VS Code development.

**Prerequisites**:
- VS Code installed
- LedgerMind MCP server running

**Steps**:

1. **Install Extension**
   ```bash
   # Install from marketplace
   code --install-extension ledgermind.vscode
   ```

2. **Configure Settings**
   ```json
   // ~/.vscode/settings.json
   {
     "ledgermind.memoryPath": "/absolute/path/to/.ledgermind",
     "ledgermind.namespace": "default",
     "ledgermind.hardcoreMode": true,
     "ledgermind.terminalMonitoring": true,
     "ledgermind.chatParticipant": true,
     "ledgermind.relevanceThreshold": 0.7
   }
   ```

3. **Verify Integration**
   ```bash
   # Open VS Code
   # Check for LedgerMind commands in Command Palette (Ctrl+Shift+P)
   # Look for: "LedgerMind: Search Decisions"
   ```

4. **Use Extension Features**
   ```bash
   # Hardcore Mode: Context automatically injected
   # Terminal Monitoring: Commands captured as evidence
   # Chat Participant: Natural language memory interaction
   ```

**Best Practices**:
- Enable hardcore mode for automated workflows
- Set appropriate relevance threshold
- Use namespace isolation for multi-project setups
- Monitor extension logs for issues

---

### Workflow: CLI Hook Integration

**Purpose**: Integrate LedgerMind into CLI-based workflows.

**Use Case**: You use CLI tools and want automatic memory capture.

**Prerequisites**:
- LedgerMind initialized
- CLI tools (Claude CLI, Gemini CLI, etc.)

**Steps**:

1. **Install Hooks**
   ```bash
   # Install hooks for specific CLI
   ledgermind install gemini --path /path/to/project
   ledgermind install cursor --path /path/to/project
   ```

2. **Configure Hook Behavior**
   ```json
   // Hook configuration (varies by CLI)
   {
     "beforePrompt": "bridge-context",
     "afterAgent": "bridge-record",
     "afterThought": "bridge-record"
   }
   ```

3. **Test Hook Integration**
   ```bash
   # Use CLI tool normally
   # Context is automatically injected
   # Interactions are automatically recorded
   ```

4. **Verify Recorded Data**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   # Check recent events
   events = bridge.get_recent_events(limit=10)

   for event in events:
       print(f"{event['kind']}: {event['description']}")
   ```

**Best Practices**:
- Test hooks before relying on them
- Monitor hook logs for errors
- Adjust context injection parameters as needed
- Keep hooks up to date with LedgerMind versions

---

## Advanced Workflows

### Workflow: Reflection and Knowledge Distillation

**Purpose**: Automatically discover patterns and extract procedural knowledge.

**Use Case**: You want to generate procedural guides from episodic events.

**Prerequisites**:
- Sufficient episodic events (100+)
- LedgerMind initialized

**Steps**:

1. **Run Reflection Engine**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   # Run reflection to discover patterns
   result = bridge.run_reflection()

   print(f"Discovered patterns: {result['patterns_found']}")
   print(f"Generated proposals: {result['proposals_generated']}")
   ```

2. **Review Generated Proposals**
   ```python
   # Get generated proposals
   proposals = bridge.get_decisions(kind="proposal", status="draft")

   for proposal in proposals:
       print(f"\n{proposal['title']}")
       print(f"  Confidence: {proposal['confidence']:.2f}")
       print(f"  Rationale: {proposal['rationale']}")
   ```

3. **Accept or Reject Proposals**
   ```python
   # Accept good proposals
   bridge.accept_proposal(fid="prop_abc123")

   # Reject bad proposals
   bridge.reject_proposal(fid="prop_xyz789")
   ```

4. **Extract Procedural Knowledge**
   ```python
   # Procedural knowledge is automatically extracted
   # from accepted proposals
   # Access via decision content
   decision = bridge.get_decisions(fid="abc123")[0]
   print(f"Procedural guide: {decision.get('procedural_guide')}")
   ```

**Best Practices**:
- Run reflection periodically (weekly)
- Review proposals before accepting
- Use distillation for common patterns
- High-quality episodic events improve reflection

---

### Workflow: Conflict Resolution

**Purpose**: Detect and resolve conflicting decisions.

**Use Case**: Multiple agents made different decisions on the same topic.

**Prerequisites**:
- Multiple decisions recorded
- Potential conflicts

**Steps**:

1. **Detect Conflicts**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   # Record new decision (may conflict)
   try:
       bridge.record_decision(
           kind="decision",
           title="Use MySQL for production",
           target="database",
           rationale="MySQL has better performance...",
           namespace="backend"
       )
   except ConflictError as e:
       print(f"Conflict detected: {e.conflicts}")
   ```

2. **Review Conflicts**
   ```python
   # Get conflicting decisions
   conflicts = e.conflicts

   for conflict in conflicts:
       print(f"\n{conflict['title']}")
       print(f"  FID: {conflict['fid']}")
       print(f"  Similarity: {conflict['similarity']:.2f}")
       print(f"  Rationale: {conflict['rationale']}")
   ```

3. **Resolve Conflict**
   ```python
   # Option 1: Supersede old decision
   bridge.supersede_decision(
       fid="old_fid",
       title="New consolidated decision",
       target="database",
       rationale="Combines best of both approaches...",
       confidence=0.9
   )

   # Option 2: Reject new decision
   bridge.reject_proposal(fid="new_fid")

   # Option 3: Create proposal for review
   bridge.record_decision(
       kind="proposal",
       title="Evaluate database options",
       target="database",
       rationale="Need to evaluate MySQL vs PostgreSQL...",
   )
   ```

4. **Verify Resolution**
   ```python
   # Check conflicts are resolved
   results = bridge.search_decisions("database")
   print(f"Active decisions: {len([r for r in results if r['status'] == 'active'])}")
   ```

**Best Practices**:
- Use arbitration modes appropriate for your setup
- Review conflicts manually when uncertain
- Supersede rather than forget for history
- Document conflict resolution rationale

---

## Performance Optimization Workflows

### Workflow: Vector Search Optimization

**Purpose**: Improve vector search performance for large memory.

**Use Case**: Vector search is slow with many decisions.

**Prerequisites**:
- Large memory (5000+ decisions)
- Vector search enabled

**Steps**:

1. **Check Current Performance**
   ```python
   import time
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   # Benchmark search
   start = time.time()
   results = bridge.search_decisions("database", limit=10)
   duration = time.time() - start

   print(f"Search time: {duration*1000:.2f}ms")
   print(f"Results: {len(results)}")
   ```

2. **Optimize Vector Workers**
   ```python
   # Reinitialize with more workers
   # (Requires restarting)
   # Current configuration in: ~/.ledgermind/config.json
   # Set: vector_workers to 2-4 (desktop), 4-8 (server)
   ```

3. **Use Embedding Cache**
   ```python
   # Cache is enabled by default
   # Cache hit rate improves with repeated queries
   # Run same query multiple times to see benefit
   ```

4. **Monitor Cache Performance**
   ```python
   # Check cache statistics (if available)
   # bridge._memory.vector_store.cache_stats()
   ```

**Best Practices**:
- Use appropriate worker count for your hardware
- Leverage cache for repeated queries
- Consider using smaller vector models on mobile
- Monitor performance over time

---

### Workflow: Memory Space Optimization

**Purpose**: Reduce memory storage footprint.

**Use Case**: Memory is using too much disk space.

**Prerequisites**:
- Large memory
- Disk space constraints

**Steps**:

1. **Check Memory Usage**
   ```bash
   # Check memory directory size
   du -sh ~/.ledgermind

   # Expected breakdown:
   # semantic/       ~10 MB (5,000 decisions @ 2KB each)
   # episodic.db     ~5 MB (10,000 events @ 500 bytes)
   # vector_index.npz ~50 MB (10,000 embeddings @ 5KB)
   ```

2. **Run Decay Process**
   ```python
   from ledgermind.core.api.bridge import IntegrationBridge

   bridge = IntegrationBridge(memory_path="~/.ledgermind")

   # Run decay to archive and forget old memories
   result = bridge.run_decay()

   print(f"Memory saved: {result['memory_freed_mb']} MB")
   ```

3. **Forget Low-Confidence Decisions**
   ```python
   # Find very low confidence decisions
   results = bridge.search_decisions("", limit=50, mode="fuzzy")

   for result in results:
       if result['confidence'] < 0.1:
           # Consider forgetting
           bridge.forget(fid=result['fid'])
   ```

4. **Adjust TTL**
   ```python
   # Use shorter TTL for faster cleanup
   # Reinitialize with TTL=7 or 14 days
   ```

**Best Practices**:
- Run decay regularly to prevent growth
- Use appropriate TTL for your use case
- Forget only truly obsolete decisions
- Monitor disk usage over time

---

## Next Steps

For integration details:
- [Integration Guide](integration-guide.md) — Client integration patterns
- [MCP Tools](mcp-tools.md) — Complete tool reference
- [VS Code Extension](vscode-extension.md) — IDE integration

For configuration:
- [Configuration](configuration.md) — All configuration options
- [Architecture](architecture.md) — System internals

For general usage:
- [Quick Start](quickstart.md) — Getting started guide
- [API Reference](api-reference.md) — Python API

---

