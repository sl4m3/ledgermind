# Configuration

Complete guide to configuring LedgerMind through environment variables, CLI flags, and configuration files.

---

## Introduction

This document covers all aspects of LedgerMind configuration for:
- **DevOps Engineers** deploying LedgerMind at scale
- **Developers** customizing behavior for specific use cases
- **Power Users** fine-tuning performance and functionality

**Configuration Priority**: When multiple sources specify the same setting, the priority is:
1. **Configuration file** (`~/.ledgermind/config.json`) — Highest
2. **Environment variables** — Medium
3. **CLI flags** — Lowest (used for one-time operations)

---

## Environment Variables

### LEDGERMIND_API_KEY

**Purpose**: Authenticate MCP server connections and control access.

**Usage**:
```bash
# Set before starting server
export LEDGERMIND_API_KEY="your-secure-random-key"

# Start server
ledgermind run --path ../.ledgermind
```

**Impact**:
- Required for MCP server connections
- Validated via `X-API-Key` header or `x-api-key`
- Missing or invalid keys return `403 Forbidden`

**Generation**:
```bash
# Generate secure random key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Or use UUID-based key
python3 -c "import uuid; print(uuid.uuid4())"
```

### LEDGERMIND_ARB_MODE

**Purpose**: Override default arbitration mode (from init or config file).

**Usage**:
```bash
# Set to 'optimal' mode for local LLM
export LEDGERMIND_ARB_MODE=optimal

# Or set to 'rich' for cloud LLM
export LEDGERMIND_ARB_MODE=rich

# Force algorithmic mode
export LEDGERMIND_ARB_MODE=lite
```

**Priority**: Overrides `arbitration_mode` in configuration file.

**Supported Values**:

| Value | Description | LLM Required |
|--------|-------------|----------------|
| `lite` | Algorithmic resolution only (fastest) | No |
| `optimal` | Local LLM (Ollama, DeepSeek) | Yes |
| `rich` | Cloud LLM (OpenAI, Anthropic) | Yes |

### Git Configuration Variables

LedgerMind respects standard Git configuration.

**GIT_AUTHOR_NAME**

Sets the author for automatic Git commits from the background worker.

```bash
export GIT_AUTHOR_NAME="LedgerMind"
```

**GIT_AUTHOR_EMAIL**

Sets the email for automatic Git commits.

```bash
export GIT_AUTHOR_EMAIL="ledgermind@system.local"
```

**GIT_COMMITTER_NAME**

Sets the committer name (for metadata tracking).

```bash
export GIT_COMMITTER_NAME="LedgerMind"
```

**GIT_COMMITTER_EMAIL**

Sets the committer email (for metadata tracking).

```bash
export GIT_COMMITTER_EMAIL="ledgermind@system.local"
```

### Path Variables

**PYTHONPATH**

Ensures Python can locate the ledgermind module.

```bash
export PYTHONPATH=/path/to/ledgermind/src:$PYTHONPATH
```

**LD_LIBRARY_PATH**

For custom GGUF model locations.

```bash
export LD_LIBRARY_PATH=/path/to/custom/libraries:$LD_LIBRARY_PATH
```

---

## CLI Flags

### Server Flags (ledgermind run)

#### `--path`

Specifies the base directory for all LedgerMind storage.

```bash
# Default: ./ledgermind (relative to current directory)
ledgermind run

# Custom path
ledgermind run --path /custom/path/to/memory
ledgermind run --path ~/.ledgermind
```

**Creates**:
- `./path/semantic/` — Markdown decision files
- `./path/episodic.db` — SQLite episodic database
- `./path/vector_index/` — Vector embeddings
- `./path/semantic_meta.db` — Metadata index
- `./path/audit.log` — Access log

#### `--name`

Sets the display name for the MCP server.

```bash
# Default: "Ledgermind"
ledgermind run --name "ProductionMemory"

# Use in multi-instance deployments
ledgermind run --name "AgentA-Memory" --namespace agent_a
ledgermind run --name "AgentB-Memory" --namespace agent_b
```

#### `--capabilities`

JSON string of feature toggles.

**Available Capabilities**:

| Capability | Description | Default |
|------------|-------------|---------|
| `sync` | Git history synchronization | `true` |
| `reflect` | Background reflection cycles | `true` |
| `decay` | Memory decay cycles | `true` |
| `purge` | GDPR deletion (forget_memory) | `true` |
| `read` | Reading decisions and events | `true` |
| `propose` | Creating proposals | `true` |
| `supersede` | Superseding decisions | `true` |
| `accept` | Accepting proposals (admin) | `true` |
| `webhooks` | Webhook notifications | `false` |

```bash
# Enable all capabilities
ledgermind run --path ../.ledgermind --capabilities '{"sync":true,"reflect":true,"decay":true,"purge":true,"read":true,"propose":true,"supersede":true,"accept":true}'

# Disable specific capabilities
ledgermind run --capabilities '{"sync":false,"reflect":false}'

# Enable only read (viewer mode)
ledgermind run --capabilities '{"read":true}'

# Combine with default role
ledgermind run --capabilities '{"webhooks":["https://my-server.com/hook"]}' --default-role AGENT
```

#### `--metrics-port`

Port number for Prometheus metrics endpoint.

```bash
# Default: 9090
ledgermind run --metrics-port 9090

# Custom port
ledgermind run --metrics-port 8080
```

**Access**:
```bash
# Check metrics
curl http://localhost:9090/metrics

# Or use Prometheus to scrape
prometheus --config.file=/path/to/prometheus.yml
```

**Exposed Metrics**:

| Metric | Type | Description |
|---------|------|-------------|
| `agent_memory_tool_calls_total` | Counter | Total MCP tool calls by tool and status |
| `agent_memory_tool_latency_seconds` | Histogram | Latency of tool calls |
| `ledgermind_phase_transitions_total` | Counter | Lifecycle phase transitions |
| `ledgermind_streams_by_vitality` | Gauge | Number of streams per vitality state |
| `ledgermind_streams_by_phase` | Gauge | Number of streams per phase |

#### `--rest-port`

Port number for REST API gateway.

```bash
# Default: None (disabled)
ledgermind run --rest-port 8080
```

**Endpoints** (when enabled):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `GET /health` | — | Server health check |
| `GET /decisions` | — | List all decisions |
| `POST /search` | — | Hybrid search |
| `GET /stats` | — | Memory statistics |

#### `--default-role`

Default access role for clients without API key.

```bash
# Default: AGENT
ledgermind run --default-role AGENT

# View-only mode
ledgermind run --default-role VIEWER
```

**Role Permissions**:

| Role | Read | Propose | Supersede | Accept | Sync | Purge |
|------|-----|-----------|---------|--------|--------|
| `VIEWER` | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| `AGENT` | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| `ADMIN` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

#### `--no-worker`

Disables the background heartbeat worker.

```bash
# Disable worker (manual control)
ledgermind run --no-worker

# Useful for debugging or resource-constrained environments
```

**Impact**:
- No automatic Git sync
- No reflection cycles
- No decay cycles
- No self-healing

#### `--verbose`

Enables debug-level logging.

```bash
# Enable verbose output
ledgermind run --verbose

# All logs to stdout
```

**Output Levels**:

| Level | Format | When to Use |
|-------|--------|-----------|
| Normal | Standard | Default operation |
| Debug | `DEBUG:` prefix | Troubleshooting |
| Error | `ERROR:` prefix | Failures only |

#### `--log-file`

Write logs to specified file instead of stdout.

```bash
# Custom log location
ledgermind run --log-file /var/log/ledgermind.log

# Combine with verbose
ledgermind run --verbose --log-file /var/log/ledgermind-debug.log
```

**Log Format**:

```
2026-03-01 10:30:45 | DEBUG | ledgermind.server.server | Starting MCP Server
2026-03-01 10:30:46 | DEBUG | ledgermind.server.server | Storage path: /path/to/memory
2026-03-01 10:30:47 | ERROR | ledgermind.server.server | Failed to load vector model
```

---

### Initialization Flags (ledgermind init)

#### Interactive Prompts

The `ledgermind init` command guides through 5 interactive prompts:

**1. Project Location**

```
Step 1: Project Location
Where is codebase for this agent? (Hooks will be installed here)
Project Path: [/current/working/directory]
```

**Recommendation**: Use the absolute path to your actual project directory (where source code lives), not the memory storage.

**2. Knowledge Core Location**

```
Step 2: Knowledge Core Location
Where should to memory database be stored?
We recommend placing it outside of project root (e.g., ../.ledgermind)
Memory Path: [../.ledgermind]
```

**Recommendation**: Place memory storage outside your project to prevent context pollution and accidental commits.

**3. Embedding Model**

```
Step 3: Embedding Model
LedgerMind uses a vector engine to semantically search your memory.
By default, we recommend to lightweight Jina 3.1.2 4-bit model (~60MB).

Choose embedder:
  jina-v5-4bit  # Recommended for mobile
  custom           # Provide URL or path to .gguf file
```

**Options**:

| Choice | Size | Use Case |
|--------|------|---------|
| `jina-v5-4bit` | ~60 MB | Mobile/Termux, fastest |
| Custom GGUF | Variable | Custom models, specific use cases |
| Transformer | 100-500 MB | Server environments, highest accuracy |

**4. Client Hooks**

```
Step 4: Client Hooks
Which client do you use?
  cursor   # Cursor IDE
  claude    # Claude Code
  gemini    # Gemini CLI
  vscode    # VS Code Extension
  none      # Manual MCP tools only
```

**Installation Behavior**:

| Client | Hooks Installed | Hook Location | Zero-Touch |
|--------|----------------|------------------|------------|
| **Claude** | UserPromptSubmit, PostToolUse, AfterModel | `~/.claude/settings.json` | ✅ |
| **Cursor** | beforeSubmitPrompt, afterAgentResponse | `~/.cursor/hooks.json` | ✅ |
| **Gemini** | BeforeAgent, AfterAgent | `.gemini/hooks/ledgermind_hook.py` | ✅ |
| **VS Code** | onDidSave, ChatParticipant | Extension config | ✅ |
| **None** | None | N/A | ❌ |

**5. Arbitration Mode**

```
Step 5: Arbitration Mode
How should to LedgerMind resolve memory conflicts and summarize knowledge?

  lite     # Algorithmic resolution only (Fast, no LLM required)
  optimal  # Local LLM via Ollama/DeepSeek (Private, medium speed)
  rich     # Cloud LLM via client (Highest quality, uses API)
```

**Mode Comparison**:

| Aspect | Lite | Optimal | Rich |
|---------|------|-------|------|
| Speed | Fastest | Medium | Slowest |
| Privacy | Complete | Local data only | External API usage |
| Quality | Good | Better | Best |
| LLM Required | No | Yes | Yes |
| Cost | Free | Compute cost | API cost |

**Configuration Persistence**:
- Arbitration mode is saved to configuration file
- Used by `IntegrationBridge.arbitrate_with_cli()`

---

## Configuration File

### File Location

```
~/.ledgermind/config.json
```

### Structure

```json
{
  "version": 1,
  "storage_path": "/absolute/path/to/memory",
  "ttl_days": 30,
  "trust_boundary": "agent_with_intent",
  "namespace": "default",
  "vector_model": "/path/to/model.gguf",
  "vector_workers": 4,
  "arbitration_mode": "optimal",
  "enable_git": true,
  "relevance_threshold": 0.7,
  "retention_turns": 10
  "capabilities": {
    "sync": true,
    "reflect": true,
    "decay": true,
    "read": true,
    "propose": true,
    "supersede": true,
    "accept": true
    "purge": false
  }
}
```

### Creating Custom Configuration

```bash
# Edit or create config file
cat > ~/.ledgermind/config.json << 'EOF'
{
  "storage_path": "/custom/memory/path",
  "ttl_days": 60,
  "arbitration_mode": "optimal"
}
EOF

# Validate config
python3 -m "import json; print(json.loads(open(' ~/.ledgermind/config.json').read()))"
```

---

## LedgermindConfig Model

### Complete Field Reference

| Field | Type | Default | Min | Max | Description |
|-------|------|-------|------|----------|-------------|
| `storage_path` | str | `"../.ledgermind"` | — | — | Absolute path to memory storage directory |
| `ttl_days` | int | `30` | 1 | 365 | Days before episodic events decay |
| `trust_boundary` | TrustBoundary | `AGENT_WITH_INTENT` | — | — | Security boundary for operations |
| `namespace` | str | `"default"` | — | — | Logical partition for memory isolation |
| `vector_model` | str | `"../.ledgermind/models/3.1.2-small-text-matching-Q4_K_M.gguf"` | — | — | Path to GGUF or Transformer model |
| `vector_workers` | int | `0` | 0 | 8 | Number of workers for vector encoding (0 = auto-detect) |
| `enable_git` | bool | `true` | — | — | Enable Git audit for semantic store |
| `relevance_threshold` | float | `0.7` | 0.0 | 1.0 | Minimum relevance score for context injection (0.0-1.0) |
| `observation_window_hours` | int | `168` | 24 | 336 | Hours for reflection temporal signals |

### Validation Rules

| Field | Validation |
|-------|----------|
| `storage_path` | Must exist or be creatable | Absolute or relative path |
| `ttl_days` | Must be >= 1 | Reasonable minimum |
| `trust_boundary` | Must be valid enum value | `AGENT_WITH_INTENT`, `HUMAN_ONLY` |
| `vector_model` | Must exist or be downloadable | Valid path to .gguf or model directory |
| `vector_workers` | Must be >= 0 | Non-negative integer |
| `relevance_threshold` | Must be 0.0 <= x <= 1.0 | Valid probability range |
| `observation_window_hours` | Must be > 0 | Positive hours |

### Default Value Sources

1. **Configuration File**: If exists, loaded first
2. **Environment Variables**: Override config file values
3. **CLI Flags**: Override environment variables
4. **Code Defaults**: Final fallback if nothing specified

**Loading Priority**: Config file > Environment variables > CLI flags > Code defaults

---

## Arbitration Modes

### Overview

Arbitration mode determines how LedgerMind resolves conflicts and enriches knowledge.

### Mode: lite

**Description**: Purely algorithmic resolution. No LLM required.

**Behavior**:
- Vector similarity analysis determines if new decision conflicts with existing ones
- Threshold: If similarity >= 70%, automatically supersede old decision
- Fast, deterministic, no external dependencies
- Good for basic conflict resolution

**Configuration**:
```bash
# Via config file
{
  "arbitration_mode": "lite"
}

# Via environment variable
export LEDGERMIND_ARB_MODE=lite
```

**Best For**:
- Production environments where consistency is critical
- Resource-constrained deployments
- Situations requiring zero external dependencies

### Mode: optimal

**Description**: Uses local LLM (Ollama, DeepSeek, etc.) for intelligent conflict resolution and knowledge summarization.

**Behavior**:
- LLM analyzes conflict between old and new decisions
- LLM determines whether to supersede, keep both, or abort
- Automatic hypothesis enrichment during reflection
- Private: All data stays on-device

**Configuration**:

```bash
# Via config file
{
  "arbitration_mode": "optimal"
}

# Via environment variable
export LEDGERMIND_ARB_MODE=optimal
```

**LLM Client Setup**:

| Provider | Environment Variable | Example |
|---------|---------------------|--------|
| **Ollama** | `OLLAMA_BASE_URL` | `export OLLAMA_BASE_URL=http://localhost:11434` |
| **DeepSeek** | `DEEPSEEK_API_KEY` | `export DEEPSEEK_API_KEY=sk-xxxxxxxxxxxx` |
| **LM Studio** | `OPENAI_BASE_URL` | `export OPENAI_BASE_URL=http://localhost:8080` |

**Best For**:
- Development teams wanting LLM assistance without cloud dependencies
- Environments with privacy requirements
- Teams already using Ollama/DeepSeek

### Mode: rich

**Description**: Uses cloud LLMs (OpenAI, Anthropic, etc.) via client API keys for highest quality resolution and knowledge summarization.

**Behavior**:
- LLM analyzes conflict with full context
- LLM generates comprehensive summaries and rationales
- Best quality results from most capable models
- External API usage (incurs costs)

**Configuration**:

```bash
# Via config file
{
  "arbitration_mode": "rich"
}

# Via environment variable
export LEDGERMIND_ARB_MODE=rich
```

**API Key Configuration**:

| Provider | Environment Variable | Setup |
|---------|---------------------|--------|
| **OpenAI** | `OPENAI_API_KEY` | `export OPENAI_API_KEY=sk-proj-...` |
| **Anthropic** | `ANTHROPIC_API_KEY` | `export ANTHROPIC_API_KEY=sk-ant-...` |
| **OpenRouter** | `OPENROUTER_API_KEY` | `export OPENROUTER_API_KEY=sk-or-...` |

**Best For**:
- Production systems requiring highest quality reasoning
- Situations where cloud API costs are acceptable
- Research projects where accuracy is paramount

---

## Trust Boundaries

### Overview

Trust boundaries control which entities can modify certain memory operations.

### Boundary: AGENT_WITH_INTENT

**Description**: Agents can perform operations with human oversight via MCP or callback.

**Allowed Operations**:
- ✅ Record decisions
- ✅ Propose decisions
- ✅ Search memory
- ✅ Record interactions
- ✅ Link evidence

**Protected Operations**:
- ❌ Accept proposals (admin only)
- ❌ Forget memories (admin only)
- ❌ Purge data (admin only)

**Protection Mechanism**:
- Human decisions (those created via MCP or marked with `[via MCP]`) cannot be superseded by agents
- Agents can only supersede decisions they created themselves

**Usage**:

```python
from ledgermind.core.api.bridge import IntegrationBridge
from ledgermind.core.core.schemas import TrustBoundary

bridge = IntegrationBridge(
    memory_path="../.ledgermind",
    trust_boundary=TrustBoundary.AGENT_WITH_INTENT
)
```

**Scenario**: Multiple agents working on same project with different namespaces, each respecting the others' decisions.

### Boundary: HUMAN_ONLY

**Description**: Only human operators can perform critical operations.

**Allowed Operations**:
- ✅ All memory operations (read, write, delete)
- ✅ Accept proposals
- ✅ Forget memories

**Protected Operations**:
- ❌ Agents cannot record/propose/supersede in this mode

**Usage**:

```bash
# Set via config file
{
  "trust_boundary": "human_only"
}

# Or environment variable
export LEDGERMIND_TRUST_BOUNDARY=human_only
```

**Scenario**: Strict control over memory for sensitive projects where human oversight is required.

---

## Performance Tuning

### TTL Configuration (ttl_days)

**Purpose**: Controls how long episodic events are kept before archiving and pruning.

**Trade-offs**:

| TTL | Disk Usage | History Coverage | Use Case |
|-----|-----------|------------------|----------|
| **7 days** | Low | Short-term only | Rapidly changing projects |
| **30 days** (default) | Medium | 1 month history | General purpose |
| **90 days** | High | 3 months history | Long-running projects |
| **365 days** | Very High | Full year history | Historical analysis |

**Configuration**:

```bash
# Via config file
{
  "ttl_days": 60
}

# Or via Memory initialization
from ledgermind.core.api.memory import Memory

memory = Memory(ttl_days=60)
```

**Memory Impact**:

```bash
# 7 days: ~1-2 GB (typical active project)
# 30 days: ~2-5 GB
# 90 days: ~5-8 GB
# 365 days: ~15-20 GB
```

### Relevance Threshold (relevance_threshold)

**Purpose**: Controls quality vs. quantity trade-off for context injection.

**Behavior**:

```python
from ledgermind.core.api.bridge import IntegrationBridge

# High threshold: Only most relevant results
bridge = IntegrationBridge(relevance_threshold=0.9)

# Low threshold: More results, less relevant
bridge = IntegrationBridge(relevance_threshold=0.5)
```

**Recommendations**:

| Threshold | When to Use |
|-----------|-------------|
| `0.9+` | Precision-critical situations | Only return highly relevant results |
| `0.7` (default) | General purpose | Balanced quality and quantity |
| `0.5-` | Exploratory searches | Return more results for discovery |

**Impact on Performance**:

Higher threshold = Fewer context injections, faster responses
Lower threshold = More context injections, slower responses

### Retention Turns (retention_turns)

**Purpose**: Prevents repeating the same context in consecutive conversation turns.

**Behavior**:

```python
# Track last N turns of context
# Avoid injecting same decision repeatedly

# After N turns, decisions "expire" from active context
```

**Configuration**:

```bash
# Via config file
{
  "retention_turns": 5
}

# Short-term (for focused sessions)
{
  "retention_turns": 3
}
```

**Trade-offs**:

| Turns | Context Relevance | Memory Usage | Use Case |
|------|------------------|------------------|----------|
| **3** | High | Low | Focused tasks, minimal redundancy |
| **10** (default) | Medium | Medium | General conversations |
| **20+** | Low | High | Long-running, less relevant |

### Vector Workers (vector_workers)

**Purpose**: Parallel encoding of embeddings for large batch operations.

**Behavior**:

```python
# Use multiprocessing for faster batch processing
memory = Memory(
    vector_workers=4  # Uses 4 CPU cores
)

# Auto-detect (default)
memory = Memory()  # Uses os.cpu_count() - 1
```

**Recommendations**:

| Environment | Workers | Reasoning |
|-----------|--------|----------|
| **Mobile (2 cores)** | 0-1 | Save battery, use default |
| **Desktop (4 cores)** | 2-3 | Balanced performance |
| **Server (8+ cores)** | 4-8 | Maximum throughput |

**Caveats**:

- More workers = More memory usage
- Too many workers = Diminishing returns
- GGUF models work best with 1-2 workers

### Observation Window (observation_window_hours)

**Purpose**: Controls temporal scope for reflection lifecycle calculations.

**Behavior**:

- **Reflection Engine**: Tracks signals over this window
- **Vitality Decay**: Days since last use compared to window
- **Phase Promotion**: Coverage relative to window size

**Values**:

| Hours | Scope | Impact |
|-------|-------|-----------|----------|
| **24** | Day | Short-term patterns |
| **168** (default) | Week | Medium-term evolution |
| **720** | Month | Long-term trends |

**Configuration**:

```bash
# Via config file
{
  "observation_window_hours": 720
}
```

---

## Client Configuration

### Claude Code

**Hook Installation**:

```bash
# Automatic install via init
ledgermind init

# Manual install
ledgermind install claude --path /path/to/project
```

**Installed Files**:

```bash
project/.ledgermind/hooks/
├── ledgermind_before_prompt.sh
└── ledgermind_after_interaction.sh
```

**Hook Behavior**:

**Before Prompt (`ledgermind_before_prompt.sh`)**:
1. Reads user prompt from stdin
2. Calls `bridge-context` command
3. Injects formatted JSON context into prompt
4. Returns modified prompt to Claude

**After Interaction (`ledgermind_after_interaction.sh`)**:
1. Reads agent response from stdin
2. Calls `bridge-record` command in background
3. Records interaction to episodic memory
4. Non-blocking for minimal latency

**Configuration File** (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "UserPromptSubmit": "/absolute/path/to/project/.ledgermind/hooks/ledgermind_before_prompt.sh",
    "PostToolUse": "/absolute/path/to/project/.ledgermind/hooks/ledgermind_after_interaction.sh",
    "AfterModel": "/absolute/path/to/project/.ledgermind/hooks/ledgermind_after_interaction.sh"
  }
}
```

### Cursor

**Hook Installation**:

```bash
ledgermind install cursor --path /path/to/project
```

**Configuration File** (`~/.cursor/hooks.json`):

```json
{
  "beforeSubmitPrompt": "/absolute/path/to/project/.ledgermind/hooks/ledgermind_before.sh",
  "afterAgentResponse": "/absolute/path/to/project/.ledgermind/hooks/ledgermind_after.sh",
  "afterAgentThought": "/absolute/path/to/project/.ledgermind/hooks/ledgermind_after.sh"
}
```

### Gemini

**Hook Installation**:

```bash
ledgermind install gemini --path /path/to/project
```

**Hook File** (`.gemini/hooks/ledgermind_hook.py`):

- Reads JSON input from stdin
- Calls appropriate bridge command
- Returns JSON output with context or confirmation

### VS Code Extension

**Installation**:

```bash
# Install from VS Code Marketplace
code --install-extension ledgermind-vscode

# Or build from source
git clone https://github.com/sl4m3/ledgermind-vscode
cd ledgermind-vscode
npm install
code .
```

**Features**:

- **Hardcore Mode**: Shadow context injection without user prompt
- **Terminal Monitoring**: Captures terminal output automatically
- **ChatParticipant**: Integrates with VS Code's AI chat
- **Configuration**: Extension settings for namespace, thresholds, etc.

**Extension Settings**:

| Setting | Description | Default |
|---------|-------------|----------|
| `memoryPath` | Path to `.ledgermind` | Auto-detected |
| `namespace` | Default namespace | `"default"` | Memory partition |
| `relevanceThreshold` | Context injection threshold | `0.7` |
| `hardcoreMode` | Enable shadow injection | `true` | Automatic context without prompts |
| `terminalMonitoring` | Capture terminal | `true` | Monitor terminal output |

---

## Common Configuration Issues

### Permission Denied on Storage Path

**Symptom**:
```
PermissionError: No permission to create storage path: /path/.ledgermind
```

**Solutions**:

```bash
# Create directory manually
mkdir -p ~/.ledgermind
chmod 755 ~/.ledgermind

# Or use user-writable location
ledgermind init
# When prompted for Memory Path, use: ~/.ledgermind
```

### Port Already in Use

**Symptom**:
```
Error: Port 9090 already in use
```

**Solutions**:

```bash
# Find what's using the port
lsof -i :9090  # Linux/macOS
netstat -an | grep 9090  # Cross-platform

# Use different port
ledgermind run --metrics-port 9091
```

### Vector Model Download Failed

**Symptom**:
```
Error: Failed to download custom model
```

**Solutions**:

```bash
# Use default model (init will prompt for jina-v5-4bit)
ledgermind init
# When prompted: "Choose embedder", select: jina-v5-4bit

# Manual download
mkdir -p ~/.ledgermind/models
curl -L -o ~/.ledgermind/models/custom.gguf https://huggingface.co/user/model/raw/main/model.gguf

# Then use custom path
ledgermind init
# When prompted for "Choose embedder", select: custom
# Provide path: ~/.ledgermind/models/custom.gguf
```

### Lock File Stuck

**Symptom**:
```
Error: Storage is currently locked by PID: 12345
```

**Solutions**:

```bash
# Wait for background worker to finish (if running)
# Check lock age (10 min = automatic break)
# Manual removal (CAUTION)
rm /path/to/.ledgermind/semantic/.lock

# Use --no-worker flag (prevents background locking)
ledgermind run --no-worker
```

### Git Not Found

**Symptom**:
```
Error: Git is not installed or not in PATH
```

**Solutions**:

```bash
# Install Git
# Ubuntu/Debian
sudo apt install git

# Termux
pkg install git

# macOS
brew install git

# Verify
git --version
```

### Vector Search Disabled

**Symptom**:
```
[WARNING] Vector search is disabled.
```

**Solutions**:

```bash
# Install GGUF support
pip install llama-cpp-python

# Or install Transformer support
pip install sentence-transformers

# Verify
python3 -c "from llama_cpp import Llama; from sentence_transformers import SentenceTransformer; print('GGUF:', bool(Llama)); print('Transformers:', bool(SentenceTransformer))"
```

---

## Next Steps

For implementation details:
- [Quick Start](quickstart.md) — Step-by-step setup
- [Integration Guide](integration-guide.md) — Client integration patterns
- [Architecture](architecture.md) — System internals
- [API Reference](api-reference.md) — Complete method signatures
- [Data Schemas](data-schemas.md) — Model definitions

For troubleshooting:
- [Common Issues](#common-configuration-issues) — See above section

For advanced configuration:
- [Workflows](workflow.md) — Operational patterns
- [MCP Tools](mcp-tools.md) — Tool-specific configuration
