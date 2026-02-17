# Agent Memory Runner (v2.4.1)

A zero-overhead PTY (Pseudo-Terminal) wrapper that injects long-term memory into ANY terminal-based AI agent.

## How it works
`am-run` creates a transparent layer between your terminal and the agent. It captures the agent's output to record new facts and injects previous knowledge into the agent's input stream at startup. In v2.4.1, it also dynamically updates the agent's context during input using a local vector store.

## Universal Support
Since it works at the terminal level (PTY), it doesn't matter what language the agent is written in or what model it uses.

### Supported Agents (Examples)
- **Gemini CLI**: `am-run gemini`
- **Claude Code**: `am-run claude`
- **Aichat**: `am-run aichat`
- **Open Interpreter**: `am-run interpreter`
- **Mods (Charm)**: `am-run mods "Analyze this code"`
- **Shell**: `am-run bash` (useful for manual auditing)

## Key Features in v2.4.1
- **Knowledge Cooldown**: Prevents context spamming by tracking recently injected knowledge in episodic memory.
- **Nudge Mechanism**: Occasionally (10% chance) prompts the agent to record new decisions when no relevant context is found.
- **Seamless Injection**: The driver automatically submits the user's query after appending context. Zero friction.
- **Verified Context**: Injected blocks are marked as `[VERIFIED KNOWLEDGE BASE]`, reducing agent hallucinations.
- **100% UX Preservation**: Re-engineered PTY driver ensures that colors, TUI, and hotkeys (Gemini, aichat) work exactly as native.
- **Dynamic Retrieval Layer (Level 3)**: Powered by a local Vector Search engine (NumPy) for sub-millisecond context lookups.
- **Smart Caching**: Built-in LRU cache reduces disk I/O and speeds up repetitive user queries.
- **Hybrid Search**: Seamlessly falls back to keyword-based search if vector dependencies are missing.
- **Environment Protocol**: Automatically instructs the agent on how to use the memory.
- **Hard Writeback**: Intercepts `MEMORY: {...}` markers and commits them to Git without asking the model.
- **Heuristic Backup**: Automatically extracts insights even if the model doesn't use markers.

## Usage
```bash
# Standard run
am-run <command> [args...]

# Run with custom memory path
am-run --path ./my_project_memory aichat

# Inject context only (raw mode)
am-run --no-protocol gemini chat
```
