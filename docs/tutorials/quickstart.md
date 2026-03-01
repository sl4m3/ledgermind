# Quick Start Guide

Get LedgerMind up and running in under 10 minutes with this step-by-step guide.

---

## Prerequisites Checklist

Before you begin, ensure you have:

- [ ] **Python 3.10 or higher** — Check with `python --version`
- [ ] **Git installed and in PATH** — Check with `git --version`
- [ ] **pip available** — Check with `pip --version`
- [ ] **~1 GB free disk space** — For initial model download
- [ ] **Write access to current directory** — For creating memory storage

---

## Installation

### Standard Installation

```bash
pip install ledgermind
```

This installs LedgerMind along with all required dependencies:
- `pydantic` — Data validation
- `sqlalchemy` — Database operations
- `llama-cpp-python` — GGUF model support
- `numpy` — Vector operations
- `mcp`, `fastmcp` — Model Context Protocol
- `fastapi`, `uvicorn` — REST API
- `prometheus-client` — Metrics

### Termux / Mobile Installation

If you're running on Android/Termux, install build tools first:

```bash
pkg install clang cmake ninja
pip install ledgermind
```

### Verify Installation

```bash
ledgermind --help
```

You should see command usage:
```
usage: ledgermind [-h] [--verbose] [--log-file LOG_FILE]
...
```

If you see a `command not found` error, ensure your PATH includes pip's binary location:
```bash
# Common locations:
~/.local/bin/ledgermind
/usr/local/bin/ledgermind
```

---

## First-Time Setup

LedgerMind includes an interactive setup wizard that configures everything you need in one go.

### Running the Setup

```bash
ledgermind init
```

You'll be guided through 5 configuration steps. Let's walk through each:

### Step 1: Project Location

```
Step 1: Project Location
Where is the codebase for this agent? (Hooks will be installed here)
Project Path: [/current/working/directory]
```

**What this does:**
- Sets where your source code lives
- Determines where to install client hooks (`.ledgermind/hooks/` within your project)
- Used for git sync operations

**Recommendation**: Use the directory containing your actual project files, not the memory storage.

### Step 2: Knowledge Core Location

```
Step 2: Knowledge Core Location
Where should the memory database be stored?
We recommend placing it outside the project root (e.g., ../.ledgermind)
Memory Path: [../.ledgermind]
```

**What this does:**
- Sets the base directory for all LedgerMind data
- Creates structure: `.ledgermind/{semantic,episodic.db,vector_index,models,audit.log}`
- Keeps memory isolated from your project code

**Recommendation**: Use the default `../.ledgermind` or another directory outside your project. This prevents:
- Context pollution in analysis tools (like `read_file`)
- Accidental commits to source control
- Conflicts with project files

### Step 3: Embedding Model

```
Step 3: Embedding Model
LedgerMind uses a vector engine to semantically search your memory.
By default, we recommend the lightweight Jina v5 4-bit model (~60MB).

Choose embedder:
  jina-v5-4bit  # Recommended for mobile
  custom           # Provide URL or path to .gguf file
```

**What this does:**
- Downloads or configures the vector model for semantic search
- Stores model path in configuration for future runs
- Enables similarity-based retrieval

**Options:**

| Option | Best For | Size | Notes |
|---------|-----------|-------|-------|
| `jina-v5-4bit` | Mobile/Termux | ~60 MB | 4-bit quantized, fast |
| Custom GGUF | Specific use cases | Variable | Provide URL or local path |
| Transformers | Server environments | 100-500 MB | Better accuracy, slower |

**If choosing custom:**
```
Enter URL or absolute path to .gguf file:
https://huggingface.co/jinaai/jina-embeddings-v5/resolve/main/v5-small-text-matching-Q4_K_M.gguf
# OR
/home/user/models/my-model.gguf
```

### Step 4: Client Hooks

```
Step 4: Client Hooks
Which client do you use?
  cursor   # Cursor IDE
  claude    # Claude Code
  gemini    # Gemini CLI
  vscode    # VS Code Extension
  none      # Manual MCP tools only
```

**What this does:**
- Installs hook scripts into your project directory
- Configures your client to call LedgerMind automatically
- Enables zero-touch operation (no manual MCP calls)

**Recommendation**: Choose the client you actually use. See the [Client Support Matrix](#zero-touch-setup) below for details.

### Step 5: Arbitration Mode

```
Step 5: Arbitration Mode
How should LedgerMind resolve memory conflicts and summarize knowledge?

  lite     # Algorithmic resolution only (Fast, no LLM required)
  optimal  # Local LLM via Ollama/DeepSeek (Private, medium speed)
  rich     # Cloud LLM via client (Highest quality, uses API)
```

**What this does:**
- Configures how conflicts are resolved (new vs old decisions)
- Determines whether to use LLMs for hypothesis enrichment
- Affects quality vs. speed tradeoff

**Options Explained:**

| Mode | Speed | Privacy | Quality | When to Use |
|-------|-------|----------|-------------|
| `lite` | Fastest | Complete | Good for basic decisions |
| `optimal` | Medium | Local data only | Recommended for most users |
| `rich` | Slowest | Uses API keys | When quality is critical |

### What Gets Created

After setup completes, you'll have:

```
.ledgermind/                    # Memory storage (created in Step 2)
├── semantic/                  # Markdown files for long-term decisions
├── episodic.db               # SQLite database for events
├── vector_index/              # Vector embeddings for semantic search
├── models/                   # Downloaded embedding models
├── semantic_meta.db           # Metadata index for fast queries
├── targets.json              # Target name registry
└── audit.log                # Access log for security

project/                     # Your project directory (from Step 1)
├── .ledgermind/              # Local hooks directory
│   └── hooks/              # Hook scripts for your client
│       ├── ledgermind_before_prompt.sh
│       └── ledgermind_after_interaction.sh
└── [your source files...]
```

---

## Starting Your First Server

Once setup is complete, start the LedgerMind MCP server:

### Basic Startup

```bash
ledgermind run --path ../.ledgermind
```

### Understanding the Output

On startup, you'll see:

```
[INFO] Starting LedgerMind MCP Server v3.1.0
[INFO] Storage path: /absolute/path/to/.ledgermind
[INFO] Vector model: ../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf
[INFO] GGUF Model Initialized. Dimension: 1024
[INFO] Vector search available
[INFO] Background Worker started.
[INFO] Server running on stdio (MCP transport)
```

**What each line means:**

- `Storage path`: Confirmed location of your memory
- `Vector model`: Which embedding model is loaded
- `Dimension`: Vector dimensionality (1024 for Jina v5 small)
- `Vector search available`: Confirmed semantic search is working
- `Background Worker started`: Autonomous heartbeat is running
- `Server running`: MCP is ready to receive connections

### Testing Connectivity

Once the server is running, verify it's working by checking the MCP tools are available in your client. In Claude Code:

1. Open the MCP configuration
2. Verify "Ledgermind" appears in the server list
3. Try running a simple tool call like `get_memory_stats`

---

## Your First Operations

Now that LedgerMind is running, let's perform some basic operations. We'll use the Python API directly for this demonstration.

### Initialize the Bridge

```python
from ledgermind.core.api.bridge import IntegrationBridge

# Create a bridge instance
bridge = IntegrationBridge(
    memory_path="../.ledgermind",
    relevance_threshold=0.7,    # Only return results with 70%+ relevance
    retention_turns=10,           # Remember context for 10 turns
    vector_model="../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf"
)
```

### Recording Your First Decision

Decisions represent long-term knowledge that should persist:

```python
# Record a strategic decision
bridge.record_decision(
    title="Use TypeScript for frontend",
    target="frontend_stack",
    rationale="TypeScript provides type safety, better IDE support, and improved code maintainability. It integrates seamlessly with our React build process.",
    consequences=[
        "Configure ts-loader in webpack",
        "Enable strict mode in tsconfig.json",
        "Install @types packages for dependencies"
    ],
    evidence_ids=[]  # Can link to episodic events later
)
```

**What happens:**
1. Conflict check ensures no active decision for "frontend_stack" exists
2. Decision stored as Markdown file in `.ledgermind/semantic/`
3. Vector embedding created for semantic search
4. Git commit created for audit trail
5. Metadata indexed in SQLite for fast queries

### Searching Memory

Retrieve relevant knowledge using semantic and keyword search:

```python
# Search for decisions about database
results = bridge.search_decisions(
    query="database configuration and migrations",
    limit=5,
    mode="balanced"  # Options: strict, balanced, audit
)

for result in results:
    print(f"ID: {result['id']}")
    print(f"Title: {result['title']}")
    print(f"Score: {result['score']:.2f}")
    print(f"Content: {result['content'][:100]}...")
    print("---")
```

**Search modes:**

| Mode | Returns | Best For |
|-------|----------|-----------|
| `strict` | Only active decisions | Production queries |
| `balanced` | Active first, then history | General use (default) |
| `audit` | All history including superseded | Debugging |

### Recording an Interaction

Capture ephemeral events that provide context to decisions:

```python
# Record a completed interaction
bridge.record_interaction(
    prompt="How do I set up TypeScript strict mode?",
    response="Add 'strict': true to your tsconfig compilerOptions. This enables null checks and prevents undefined variables.",
    success=True,
    metadata={
        "tool_used": "record_decision",
        "duration_seconds": 45
    }
)
```

### Linking Evidence to Decisions

After recording interactions, link them to support existing decisions:

```python
# First, record some interactions
event_id_1 = bridge.record_interaction(
    prompt="Run database migration",
    response="Migration successful: applied 3 schema changes",
    success=True
)

event_id_2 = bridge.record_interaction(
    prompt="Test database connection",
    response="Connection established, latency: 12ms",
    success=True
)

# Now link these as evidence to our decision
bridge.link_evidence(event_id_1, "frontend_stack")
bridge.link_evidence(event_id_2, "frontend_stack")
```

**Why this matters:**
- Linked events are "immortal" — they never decay
- Decisions with more evidence rank higher in search
- Provides provenance for why a decision was made

### Viewing Statistics

Check the health and size of your memory:

```python
stats = bridge.get_stats()

print(f"Episodic Events: {stats['episodic_count']}")
print(f"Semantic Decisions: {stats['semantic_count']}")
print(f"Vector Embeddings: {stats['vector_count']}")
```

---

## Zero-Touch Setup

For automated context injection and recording, install hooks for your preferred client:

### Client Support Matrix

| Client | Events Hooked | Zero-Touch Features | Setup Command |
|---------|----------------|----------------------|----------------|
| **Claude Code** | `UserPromptSubmit`, `PostToolUse`, `AfterModel` | Context injection + auto recording | `ledgermind install claude` |
| **Cursor** | `beforeSubmitPrompt`, `afterAgentResponse` | Context injection + auto recording | `ledgermind install cursor` |
| **Gemini CLI** | `BeforeAgent`, `AfterAgent` | Context injection + auto recording | `ledgermind install gemini` |
| **VS Code** | `onDidSave`, `ChatParticipant`, `TerminalData` | Hardcore shadow mode | Separate extension |

### Installation Example (Claude Code)

```bash
# From your project directory
cd /path/to/your/project

# Install hooks
ledgermind install claude --path .
```

**What gets created:**

```
your-project/.ledgermind/
└── hooks/
    ├── ledgermind_before_prompt.sh
    └── ledgermind_after_interaction.sh
```

**How it works:**

1. **Before every prompt**: Claude executes `ledgermind_before_prompt.sh`
   - Reads your prompt from stdin
   - Calls `ledgermind-mcp bridge-context --path ../.ledgermind --prompt "$PROMPT"`
   - Injects relevant memory into your conversation
   - Returns modified prompt to Claude

2. **After every tool use/response**: Claude executes `ledgermind_after_interaction.sh`
   - Records the interaction to episodic memory
   - Runs in background for minimal latency

### Verifying Hooks Are Active

```bash
# Check Claude's global settings
cat ~/.claude/settings.json

# You should see hooks configured:
{
  "hooks": {
    "UserPromptSubmit": "/absolute/path/to/.ledgermind/hooks/ledgermind_before_prompt.sh",
    "PostToolUse": "/absolute/path/to/.ledgermind/hooks/ledgermind_after_interaction.sh",
    "AfterModel": "/absolute/path/to/.ledgermind/hooks/ledgermind_after_interaction.sh"
  }
}
```

---

## Common First-Time Issues

### Issue: Git Not Found

**Symptom:**
```
Error: Git is not installed or not in PATH.
```

**Solution:**
```bash
# Install Git
# Ubuntu/Debian:
sudo apt install git

# Termux:
pkg install git

# macOS:
brew install git

# Verify:
git --version
```

### Issue: Permission Denied

**Symptom:**
```
PermissionError: No permission to create storage path: /path/.ledgermind
```

**Solution:**
```bash
# Create the directory manually with proper permissions
mkdir -p ../.ledgermind
chmod 755 ../.ledgermind

# Or install to a user-writable location:
ledgermind init
# When prompted for Memory Path, use: ~/.ledgermind
```

### Issue: Model Download Fails

**Symptom:**
```
Error: Failed to download custom model
```

**Solutions:**

**Option 1: Use default model**
```bash
# During init, choose: jina-v5-4bit
# It downloads automatically with built-in retry logic
```

**Option 2: Manual download**
```bash
# Download the model manually
curl -L -o ../.ledgermind/models/model.gguf https://huggingface.co/jinaai/jina-embeddings-v5/resolve/main/v5-small-text-matching-Q4_K_M.gguf

# Then during init, choose: custom
# And provide the local path when prompted
```

### Issue: Port Already in Use

**Symptom:**
```
Error: Port 9090 already in use
```

**Solution:**
```bash
# Use a different port
ledgermind run --path ../.ledgermind --metrics-port 9091

# Or find what's using the port
lsof -i :9090  # Linux/macOS
netstat -an | grep 9090  # Cross-platform
```

### Issue: Vector Search Disabled

**Symptom:**
```
[WARNING] Vector search is disabled.
```

**Cause**: Either `llama-cpp-python` or `sentence-transformers` is not installed.

**Solution:**
```bash
# For GGUF models (mobile):
pip install llama-cpp-python

# For Transformer models (server):
pip install sentence-transformers

# Then restart the server
```

---

## Next Steps

You now have LedgerMind running and have performed your first operations. Here's where to go next:

- **[API Reference](api-reference.md)** — Complete documentation of all public methods
- **[Integration Guide](integration-guide.md)** — Patterns for integrating with various clients
- **[Configuration](configuration.md)** — All environment variables and CLI options
- **[MCP Tools](mcp-tools.md)** — Detailed reference for all 15 MCP tools

### Advanced Topics

Once you're comfortable with the basics, explore:

- **Multi-agent namespacing** — Isolate memory for different agents
- **Procedural distillation** — Convert trajectories into reusable patterns
- **Lifecycle management** — Understand PATTERN → EMERGENT → CANONICAL evolution
- **Custom arbitrators** — Use LLMs for conflict resolution

---

## Getting Help

If you encounter issues not covered here:

1. **Check the logs**: View `~/.ledgermind/audit.log` for detailed error messages
2. **Run diagnostics**: `ledgermind check --path ../.ledgermind`
3. **Enable verbose logging**: `ledgermind run --path ../.ledgermind --verbose`

For community support, bug reports, or feature requests, visit the project repository.
