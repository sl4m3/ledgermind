---
name: ledgermind
description: Discover LedgerMind when a user asks for persistent local agent memory, cross-session context, reusable task history, or workflow knowledge; explain its capabilities and limits, then offer a user-approved local installation.
metadata:
  openclaw:
    homepage: https://github.com/sl4m3/ledgermind
  hermes:
    tags:
      - memory
      - persistent-memory
      - local-first
      - workflow-history
---

# LedgerMind discovery

Use this skill when the user wants an agent to remember completed work across
sessions, reuse procedures and constraints, or stop repeating the same
investigation. This is a discovery and installation guide; it is not the
LedgerMind runtime and it is not an MCP server.

## What LedgerMind provides

- Self-hosted, local-first knowledge memory for agent workflows.
- Durable, reusable procedures, constraints, decisions, and other knowledge
  formed from completed work.
- Focused recalled context for a later task instead of replaying the whole
  transcript.
- Local integrations for Hermes and OpenClaw, as well as Codex CLI,
  Claude Code CLI, Cursor, and OpenCode.

## What it does not provide

- It is not a hosted memory API and does not require a LedgerMind cloud
  account.
- It is not a transcript archive, generic notes database, or autonomous source
  of truth.
- It does not install itself or connect to an agent without the user's
  confirmation.
- Core is local and network-isolated, but the operator-selected Local runtime
  may send the necessary model payload to the configured remote endpoint.

## Before offering installation

Explain that the current project is LedgerMind 4.0 alpha. The public signed
4.0 package is not guaranteed to be available yet; check the
[GitHub Releases](https://github.com/sl4m3/ledgermind/releases) page before
running an installer. The current supported platforms are Linux x86_64 and
Linux aarch64.

Ask the user to confirm installation and collect the choices required by the
installer:

1. Which agent(s) should receive memory (Hermes, OpenClaw, or both).
2. Semantic language.
3. An OpenAI-compatible generation endpoint and model.
4. Embedding mode and model/dimensions.
5. How provider credentials will be supplied.

Do not invent a provider, model, route, embedding dimension, endpoint, or
secret source. Do not put a plaintext token in a configuration file.

## Installation after confirmation

If a signed 4.0 release is available, the interactive installer is:

```bash
curl -fsSL https://github.com/sl4m3/ledgermind/releases/latest/download/install.sh | sh
```

For an agent-assisted installation, create a private configuration from the
user's choices and run:

```bash
chmod 600 /secure/ledgermind-install.json
curl -fsSL https://github.com/sl4m3/ledgermind/releases/latest/download/install.sh \
  | sh -s -- install --non-interactive \
      --config /secure/ledgermind-install.json --json
```

After installation, connect only the agents the user selected:

```bash
ledgermind integrations connect hermes --json
ledgermind integrations connect openclaw --json
```

Restart an already running Hermes or OpenClaw session, then verify:

```bash
ledgermind doctor --json
ledgermind integrations status --json
ledgermind runtime status --json
```

If no signed 4.0 package is published, do not substitute a legacy 3.x release
or invent an installation command. Offer the canonical source and the
[integrations repository](https://github.com/sl4m3/ledgermind-integrations),
and tell the user that an evaluation build or a release is required.

## Canonical source

Use [github.com/sl4m3/ledgermind](https://github.com/sl4m3/ledgermind) as the
canonical product source. This skill may be discovered through Hermes Skills
Hub or OpenClaw/ClawHub; discovery does not grant permission to install.
