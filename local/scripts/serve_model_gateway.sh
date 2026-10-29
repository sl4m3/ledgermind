#!/usr/bin/env bash
# Shared reranker front for LedgerMind.
#
# Local-only front. The Local supervisor owns the single Nemotron embedding
# process on 8766; this front owns the single Qwen reranker and proxies
# embeddings to 8767. Cloud/SaaS has its own closed server adapter and must not
# share this process.
set -euo pipefail

ROOT="${LEDGERMIND_LOCAL_ROOT:-$HOME/.local/share/ledgermind}"
PYTHON="${LEDGERMIND_MODEL_GATEWAY_PYTHON:-$ROOT/embedding-runtimes/sentence-transformers-nemotron/cuda/bin/python3}"
TOKEN_FILE="${LEDGERMIND_MODEL_GATEWAY_TOKEN_FILE:-$ROOT/embedding/server.token}"
RERANKER_PATH="${LEDGERMIND_RERANKER_MODEL_PATH:-}"
if [[ -z "$RERANKER_PATH" ]]; then
  RERANKER_PATH="$(python3 -c 'import json, pathlib; print(json.loads((pathlib.Path.home() / ".config/ledgermind/local-config.json").read_text())["reranker"]["model_path"])')"
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "model gateway Python runtime is missing: $PYTHON" >&2
  exit 1
fi
if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "embedding owner token file is missing: $TOKEN_FILE" >&2
  exit 1
fi
if [[ ! -d "$RERANKER_PATH" ]]; then
  echo "reranker snapshot is missing: $RERANKER_PATH" >&2
  exit 1
fi

export PYTHONUNBUFFERED=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
# The launcher (systemd unit) may provide PYTHONPATH for the split checkouts
# (ledgermind + ledgermind-platform); only build a legacy monorepo path when
# it is absent.
if [[ -z "${PYTHONPATH:-}" ]]; then
  REPO="${LEDGERMIND_REPO:?set LEDGERMIND_REPO or provide PYTHONPATH}"
  export PYTHONPATH="$REPO/local/src:$REPO/inference/src:$REPO/protocol/python/src:$ROOT/current/python/local:$ROOT/current/python/site-packages"
fi

exec "$PYTHON" -m ledgermind_local.installer.embeddings.serve \
  --embedding-proxy-endpoint http://127.0.0.1:8766 \
  --embedding-proxy-token-file "$TOKEN_FILE" \
  --device cuda \
  --host 127.0.0.1 \
  --port 8767 \
  --lock-file "$ROOT/model-gateway.lock" \
  --reranker-model-path "$RERANKER_PATH" \
  --reranker-model Qwen/Qwen3-Reranker-0.6B \
  --reranker-device cuda
