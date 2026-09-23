# syntax=docker/dockerfile:1

FROM python:3.12-bookworm AS python-runtime

FROM node:22-bookworm-slim

ARG CODEX_VERSION=0.147.0
ARG CLAUDE_VERSION=2.1.233
ARG OPENCODE_VERSION=1.18.16
ARG OPENCLAW_VERSION=2026.7.1-2
ARG HERMES_REF=aebab05f9ec08c29672dd709db2e639d00a8544a

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DISABLE_AUTOUPDATER=1 \
    DISABLE_UPDATES=1

# The signed smoke bundle is built for CPython 3.12. Copy the matching runtime
# into the otherwise Node-based agent image so native Python wheels are tested
# against the ABI declared by the artifact, not whichever Python Debian ships.
COPY --from=python-runtime /usr/local /usr/local

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash bubblewrap build-essential ca-certificates curl git jq python3 python3-pip python3-venv \
        pipx ripgrep tini zstd \
    && npm install --global \
        "@openai/codex@${CODEX_VERSION}" \
        "@anthropic-ai/claude-code@${CLAUDE_VERSION}" \
        "opencode-ai@${OPENCODE_VERSION}" \
        "openclaw@${OPENCLAW_VERSION}" \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 --shell /bin/bash smoke

USER smoke
ENV HOME=/home/smoke \
    PATH=/home/smoke/.local/bin:/home/smoke/.opencode/bin:/usr/local/bin:/usr/bin:/bin \
    HERMES_HOME=/home/smoke/.hermes \
    CODEX_HOME=/home/smoke/.codex \
    CLAUDE_CONFIG_DIR=/home/smoke/.claude \
    CURSOR_HOME=/home/smoke/.cursor \
    OPENCODE_CONFIG_DIR=/home/smoke/.config/opencode

RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- \
        --commit "${HERMES_REF}" --force-commit --skip-setup \
        --skip-browser --skip-computer-use --no-skills --non-interactive \
    && curl -fsSL https://cursor.com/install | bash \
    && mkdir -p \
        "$HERMES_HOME" "$CODEX_HOME" "$CLAUDE_CONFIG_DIR" \
        "$CURSOR_HOME" "$OPENCODE_CONFIG_DIR" \
    && hermes --version \
    && codex --version \
    && claude --version \
    && cursor-agent --version \
    && opencode --version \
    && openclaw --version

COPY --chown=smoke:smoke --chmod=0755 smoke.sh /usr/local/bin/ledgermind-integration-smoke

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/ledgermind-integration-smoke"]
