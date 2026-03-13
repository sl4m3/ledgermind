# Quick Start Guide

Get LedgerMind up and running in 10 minutes.

---

## Introduction

This guide walks you through installing, configuring, and using LedgerMind for the first time. By the end, you'll have:

- A fully initialized memory system
- Client hooks installed for your preferred LLM
- Your first decision recorded and retrieved

**Time Required**: 10-15 minutes

**Prerequisites**:
- Python 3.10+
- Git installed
- pip package manager

---

## Step 1: Install LedgerMind

### Standard Installation

```bash
# Install from PyPI
pip install ledgermind
```

### For Termux/Android Users

```bash
# Install build tools first
pkg install clang cmake ninja python

# Then install LedgerMind
pip install ledgermind
```

### Verify Installation

```bash
ledgermind --help
```

Expected output:
```
usage: ledgermind [-h] [--verbose] [--log-file LOG_FILE] ...

LedgerMind - Autonomous Memory Management System
```

---

## Step 2: Initialize Your Memory

Run the interactive initialization:

```bash
ledgermind init
```

You'll be guided through 6 steps:

### Step 2.1: Project Location

```
Step 1: Project Location
Where is the codebase for this agent? (Hooks will be installed here)
Project Path: [/current/working/directory]
```

**Recommendation**: Use your actual project directory where source code lives.

```bash
# Example
Project Path: /home/user/my-project
```

### Step 2.2: Memory Path

```
Step 2: Knowledge Core Location
Where should the memory database be stored?
We recommend placing it outside the project root (e.g., ../.ledgermind)
Memory Path: [../.ledgermind]
```

**Recommendation**: Place memory outside your project to prevent accidental commits.

```bash
# Default is fine for most cases
Memory Path: ../.ledgermind

# Or use home directory
Memory Path: ~/.ledgermind
```

### Step 2.3: Embedding Model

```
Step 3: Embedding Model
LedgerMind uses a vector engine to semantically search your memory.
By default, we recommend the lightweight Jina v5 4-bit model (~60MB).

Choose embedder:
  > jina-v5-4bit  # Recommended for mobile
    custom        # Provide URL or path to .gguf file
```

**Options**:

| Choice | Size | Best For |
|--------|------|----------|
| `jina-v5-4bit` | ~60 MB | Mobile/Termux, fastest setup |
| `custom` | Variable | Specific model requirements |

**Recommendation**: Use `jina-v5-4bit` for most cases.

### Step 2.4: Client Hooks

```
Step 4: Client Hooks
We can install hooks to seamlessly capture context for your preferred client.

Which client do you use?
  > cursor    # Cursor IDE
    claude    # Claude Code
    gemini    # Gemini CLI
    vscode    # VS Code Extension
    none      # Manual MCP tools only
```

**Recommendation**: Choose your primary development client for automatic context injection.

### Step 2.5: Enrichment Mode

```
Step 5: Enrichment Mode
How should LedgerMind resolve memory conflicts and summarize knowledge?

  > optimal  # Local LLM via Ollama/DeepSeek (Private, medium speed)
    rich     # Cloud LLM via client (Highest quality, uses API)
```

**Comparison**:

| Mode | LLM Required | Privacy | Quality | Speed |
|------|--------------|---------|---------|-------|
| `optimal` | Local (Ollama) | High | Good | Fast |
| `rich` | Cloud API | Lower | Best | Slower |

**Recommendation**: Start with `optimal` for privacy. Switch to `rich` for production.

### Step 2.6: Language Preference

```
Step 6: Language Preference
Enter preferred language for records (e.g., 'russian', 'english', 'german'):
Preferred language: [russian]
```

**Recommendation**: Use the language you'll write most decisions in.

---

## Step 3: Start the MCP Server

### Basic Start

```bash
ledgermind run --path ../.ledgermind
```

### With REST API Gateway

```bash
# Enable REST API on port 8080
ledgermind run --path ../.ledgermind --rest-port 8080

# Access via HTTP
curl http://localhost:8080/health
```

### With Metrics

```bash
# Enable Prometheus metrics on port 9090
ledgermind run --path ../.ledgermind --metrics-port 9090

# View metrics
curl http://localhost:9090/metrics
```

### With API Key Authentication

```bash
# Set API key
export LEDGERMIND_API_KEY="your-secure-random-key"

# Start server
ledgermind run --path ../.ledgermind

# Clients must now provide X-API-Key header
```

---

## Step 4: Record Your First Decision

### Via Python API

```python
from ledgermind.core.api.bridge import IntegrationBridge

# Initialize bridge
bridge = IntegrationBridge(memory_path="../.ledgermind")

# Record a decision
bridge.record_decision(
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
    confidence=0.9
)

print("✓ Decision recorded!")
```

### Via MCP Tool

```python
# If using MCP client
result = client.call_tool("record_decision", {
    "title": "Use PostgreSQL for production database",
    "target": "database",
    "rationale": "ACID compliance and proven reliability...",
    "consequences": ["Migrate from SQLite", "Set up pooling"]
})
```

### Verify Recording

```python
# Search for the decision
results = bridge.search_decisions("PostgreSQL", limit=1)

if results:
    print(f"✓ Found: {results[0]['title']}")
    print(f"  Score: {results[0]['score']:.2f}")
    print(f"  Confidence: {results[0]['confidence']:.2f}")
```

---

## Step 5: Get Context for a Prompt

```python
# Get relevant context for a question
context = bridge.get_context_for_prompt(
    "How should I handle database migrations?",
    limit=3
)

print(context)
```

**Output Format**:

```json
{
  "source": "ledgermind",
  "memories": [
    {
      "id": "abc123",
      "title": "Use PostgreSQL for production database",
      "target": "database",
      "score": 0.92,
      "status": "active",
      "kind": "decision",
      "rationale": "PostgreSQL provides ACID compliance...",
      "consequences": ["Migrate from SQLite", ...]
    }
  ]
}
```

---

## Step 6: Install Client Hooks (Optional)

For automatic context injection without manual API calls:

### Claude Code

```bash
ledgermind install claude --path /path/to/project
```

**Hooks Installed**:
- `UserPromptSubmit` — Injects context before each prompt
- `Stop` — Records interactions after response

### Cursor IDE

```bash
ledgermind install cursor --path /path/to/project
```

**Hooks Installed**:
- `beforeSubmitPrompt` — Context injection
- `afterAgentResponse` — Auto-record interaction

### Gemini CLI

```bash
ledgermind install gemini --path /path/to/project
```

**Hooks Installed**:
- `BeforeAgent` — Context injection
- `AfterAgent` — Auto-record interaction

### VS Code Extension

```bash
# Install extension
code --install-extension ledgermind-vscode

# Configure in settings.json
{
  "ledgermind.memoryPath": "/absolute/path/to/.ledgermind",
  "ledgermind.hardcoreMode": true,
  "ledgermind.terminalMonitoring": true
}
```

---

## Step 7: Verify Everything Works

### Check Health

```python
from ledgermind.core.api.bridge import IntegrationBridge

bridge = IntegrationBridge(memory_path="../.ledgermind")
health = bridge.check_health()

print(f"Git Available: {'✓' if health['git_available'] else '✗'}")
print(f"Storage Writable: {'✓' if health['storage_writable'] else '✗'}")
print(f"Vector Search: {'✓' if health['vector_available'] else '(!) Disabled'}")
```

### Get Statistics

```python
stats = bridge.get_stats()

print(f"Episodic Events: {stats['episodic_count']}")
print(f"Semantic Decisions: {stats['semantic_count']}")
print(f"Vector Embeddings: {stats['vector_count']}")
```

---

## Next Steps

### Daily Usage

```python
# Before coding — get context
context = bridge.get_context_for_prompt("Implementing user authentication")

# After coding — record decision
bridge.record_decision(
    title="Use JWT tokens for authentication",
    target="auth",
    rationale="Stateless and scales well..."
)

# Record interaction
bridge.record_interaction(
    prompt="Implement login endpoint",
    response="200 OK - Login successful",
    success=True
)
```

### Explore Advanced Features

| Feature | Command | Description |
|---------|---------|-------------|
| **Supersede Decision** | `bridge.supersede_decision()` | Replace outdated decisions |
| **Accept Proposal** | `bridge.accept_proposal()` | Promote proposals to decisions |
| **View History** | `bridge.get_decision_history(fid)` | See decision evolution |
| **Run Decay** | `bridge.run_decay()` | Archive old events |
| **Sync Git** | `bridge.sync_git()` | Index Git commits |
| **Visualize Graph** | `bridge.generate_knowledge_graph()` | Mermaid diagram |

### Configure Advanced Settings

See [Configuration](configuration.md) for:
- Environment variables
- TTL tuning
- Vector worker configuration
- Trust boundaries

### Learn About MCP Tools

See [MCP Tools](mcp-tools.md) for all 15 available tools with examples.

---

## Troubleshooting

### Issue: "Git is not installed"

```bash
# Install Git
# Ubuntu/Debian
sudo apt install git

# Termux
pkg install git

# macOS
brew install git
```

### Issue: "Permission denied"

```bash
# Create directory manually
mkdir -p ../.ledgermind
chmod 755 ../.ledgermind

# Or use home directory
ledgermind init
# When prompted, use: ~/.ledgermind
```

### Issue: "Vector search is disabled"

```bash
# For GGUF models
pip install llama-cpp-python

# For Transformer models
pip install sentence-transformers

# Restart server
```

### Issue: "Port already in use"

```bash
# Find what's using the port
lsof -i :9090  # Linux/macOS

# Use different port
ledgermind run --path ../.ledgermind --metrics-port 9091
```

---

## Quick Reference

### Common Commands

```bash
# Initialize
ledgermind init

# Run server
ledgermind run --path ../.ledgermind

# Install hooks
ledgermind install claude --path /path/to/project

# Check health
ledgermind check --path ../.ledgermind

# View stats
ledgermind stats --path ../.ledgermind
```

### Common Python API Calls

```python
from ledgermind.core.api.bridge import IntegrationBridge

bridge = IntegrationBridge(memory_path="../.ledgermind")

# Record
bridge.record_decision(title, target, rationale)
bridge.supersede_decision(title, target, rationale, old_ids)
bridge.accept_proposal(proposal_id)

# Search
bridge.search_decisions(query, limit=5)
bridge.get_decisions(target="database")
bridge.get_decision_history(fid)

# Context
bridge.get_context_for_prompt(prompt, limit=3)
bridge.record_interaction(prompt, response, success)

# Maintenance
bridge.run_decay()
bridge.sync_git()
```

---

## What's Next?

1. **[Architecture](architecture.md)** — Understand how LedgerMind works internally
2. **[Configuration](configuration.md)** — Tune settings for your environment
3. **[Integration Guide](integration-guide.md)** — Deep dive into client integration
4. **[Workflows](workflow.md)** — Common operational patterns

---

*You're now ready to use LedgerMind v3.3.0! Start recording decisions and let the autonomous memory system work for you.*
