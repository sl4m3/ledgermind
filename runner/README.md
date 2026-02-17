# Agent Memory Runner (v2.1.1)

A zero-overhead PTY (Pseudo-Terminal) wrapper that injects long-term memory into ANY terminal-based AI agent.

## How it works
`am-run` creates a transparent layer between your terminal and the agent. It captures the agent's output to record new facts and injects previous knowledge into the agent's input stream at startup.

## Universal Support
Since it works at the terminal level (PTY), it doesn't matter what language the agent is written in or what model it uses.

### Supported Agents (Examples)
- **Gemini CLI**: `am-run gemini`
- **Claude Code**: `am-run claude`
- **Aichat**: `am-run aichat`
- **Open Interpreter**: `am-run interpreter`
- **Mods (Charm)**: `am-run mods "Analyze this code"`
- **Shell**: `am-run bash` (useful for manual auditing)

## Key Features
- **100% UX Preservation**: Colors, TUI, and hotkeys work exactly as native.
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
