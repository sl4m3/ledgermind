# Agent integration container smoke

This image installs real Hermes, Codex CLI, Claude Code, Cursor Agent,
OpenCode, and OpenClaw distributions. The runtime test then installs a signed
LedgerMind bundle, connects all detected clients, executes lifecycle hooks,
validates the JavaScript plugins, and runs the Hermes and OpenClaw plugin
diagnostics without provider calls.

Build and run from this directory:

```bash
docker build -t ledgermind-agent-integration-smoke .
docker run --rm \
  -v /absolute/path/to/signed-platform-artifacts:/artifacts:ro \
  -v /absolute/path/to/reports:/reports \
  ledgermind-agent-integration-smoke
```

The container uses a disposable home directory and never mounts the host's
agent configuration.
