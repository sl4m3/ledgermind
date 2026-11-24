#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)"
ARTIFACTS_DIR="${LEDGERMIND_V5_ARTIFACTS:-/tmp/ledgermind-v5-artifacts}"

if [[ -z "${LEDGERMIND_GENERATION_TOKEN:-}" ]]; then
    printf 'Set LEDGERMIND_GENERATION_TOKEN before running real-API Docker E2E.\n' >&2
    exit 2
fi

docker build -t ledgermind-e2e -f "${SCRIPT_DIR}/Dockerfile" "${SCRIPT_DIR}"

docker run --rm \
    --security-opt seccomp=unconfined \
    --security-opt apparmor=unconfined \
    -e LEDGERMIND_GENERATION_TOKEN \
    -e "LEDGERMIND_EMBEDDING_TOKEN=${LEDGERMIND_EMBEDDING_TOKEN:-$LEDGERMIND_GENERATION_TOKEN}" \
    -e "LEDGERMIND_DECISION_TOKEN=${LEDGERMIND_DECISION_TOKEN:-$LEDGERMIND_GENERATION_TOKEN}" \
    -e "LEDGERMIND_GENERATION_PROVIDER=${LEDGERMIND_GENERATION_PROVIDER:-openrouter}" \
    -e "LEDGERMIND_GENERATION_ENDPOINT=${LEDGERMIND_GENERATION_ENDPOINT:-https://openrouter.ai/api/v1}" \
    -e "LEDGERMIND_GENERATION_MODEL=${LEDGERMIND_GENERATION_MODEL:-deepseek/deepseek-v4-flash-0731}" \
    -e "LEDGERMIND_GENERATION_ROUTE=${LEDGERMIND_GENERATION_ROUTE:-deepinfra/fp8}" \
    -e "LEDGERMIND_EMBEDDING_ENDPOINT=${LEDGERMIND_EMBEDDING_ENDPOINT:-https://openrouter.ai/api/v1}" \
    -e "LEDGERMIND_EMBEDDING_MODEL=${LEDGERMIND_EMBEDDING_MODEL:-nvidia/nemotron-3.5-embed-1b:free}" \
    -e "LEDGERMIND_EMBEDDING_DIMENSIONS=${LEDGERMIND_EMBEDDING_DIMENSIONS:-2048}" \
    -v "${REPO_ROOT}:/workspace:ro" \
    -v "${ARTIFACTS_DIR}:/artifacts:ro" \
    ledgermind-e2e bash -lc '
set -euo pipefail
python3 /workspace/local/tests/container/e2e/build_test_release.py \
    --artifacts /artifacts \
    --workspace /workspace \
    --output /tmp/test-release

PUB_B64=$(cat /tmp/test-release/public_key.b64)
su - e2e -c "
set -euo pipefail
mkdir -p ~/.codex
export LEDGERMIND_INSTALLER_PUBLIC_KEY=\"${PUB_B64}\"
export LEDGERMIND_GENERATION_TOKEN=\"${LEDGERMIND_GENERATION_TOKEN}\"
export LEDGERMIND_EMBEDDING_TOKEN=\"${LEDGERMIND_EMBEDDING_TOKEN}\"
export LEDGERMIND_DECISION_TOKEN=\"${LEDGERMIND_DECISION_TOKEN}\"
export LEDGERMIND_GENERATION_PROVIDER=\"${LEDGERMIND_GENERATION_PROVIDER}\"
export LEDGERMIND_GENERATION_ENDPOINT=\"${LEDGERMIND_GENERATION_ENDPOINT}\"
export LEDGERMIND_GENERATION_MODEL=\"${LEDGERMIND_GENERATION_MODEL}\"
export LEDGERMIND_GENERATION_ROUTE=\"${LEDGERMIND_GENERATION_ROUTE}\"
export LEDGERMIND_EMBEDDING_ENDPOINT=\"${LEDGERMIND_EMBEDDING_ENDPOINT}\"
export LEDGERMIND_EMBEDDING_MODEL=\"${LEDGERMIND_EMBEDDING_MODEL}\"
export LEDGERMIND_EMBEDDING_DIMENSIONS=\"${LEDGERMIND_EMBEDDING_DIMENSIONS}\"

python3 - <<PY
import json, os
from pathlib import Path
gen = {
    \"provider_profile\": os.environ[\"LEDGERMIND_GENERATION_PROVIDER\"],
    \"endpoint\": os.environ[\"LEDGERMIND_GENERATION_ENDPOINT\"],
    \"model\": os.environ[\"LEDGERMIND_GENERATION_MODEL\"],
    \"token_env\": \"LEDGERMIND_GENERATION_TOKEN\",
}
if os.environ.get(\"LEDGERMIND_GENERATION_ROUTE\"):
    gen[\"route\"] = os.environ[\"LEDGERMIND_GENERATION_ROUTE\"]
cfg = {
    \"schema_version\": 2,
    \"semantic_language\": \"en\",
    \"memory_mode\": \"shared\",
    \"integrations\": [{\"id\": \"codex\", \"enabled\": True}],
    \"generation\": gen,
    \"resolution_decision\": {\"backend\": \"jev\", \"token_env\": \"LEDGERMIND_DECISION_TOKEN\"},
    \"embedding\": {
        \"mode\": \"api\",
        \"api\": {
            \"endpoint\": os.environ[\"LEDGERMIND_EMBEDDING_ENDPOINT\"],
            \"model\": os.environ[\"LEDGERMIND_EMBEDDING_MODEL\"],
            \"dimensions\": int(os.environ[\"LEDGERMIND_EMBEDDING_DIMENSIONS\"]),
            \"token_env\": \"LEDGERMIND_EMBEDDING_TOKEN\",
        },
    },
}
p = Path(\"/tmp/real-install.json\")
p.write_text(json.dumps(cfg, indent=2), encoding=\"utf-8\")
p.chmod(0o600)
PY

echo \"=== Installing with real OpenRouter config (model=${LEDGERMIND_GENERATION_MODEL}, route=${LEDGERMIND_GENERATION_ROUTE:-auto}, embed=${LEDGERMIND_EMBEDDING_MODEL}) ===\"
if ! {
    set +e
    /tmp/test-release/ledgermind-installer-linux-x86_64 install \
        --non-interactive \
        --config /tmp/real-install.json \
        --manifest /tmp/test-release/install-manifest.json \
        --manifest-signature /tmp/test-release/install-manifest.sig \
        --bundle /tmp/test-release/ledgermind-linux-x86_64.tar.zst \
        --json >/tmp/real-install-result.json
    rc=\$?
    set -e
    test \"\$rc\" -eq 0
}; then
    echo \"Installer failed with exit code \$rc:\" >&2
    cat /tmp/real-install-result.json >&2 || true
    exit \"\$rc\"
fi

echo \"=== Verifying ledgermind doctor & core doctor ===\"
DOCTOR_JSON=\$(~/.local/bin/ledgermind doctor --json || true)
if ! printf \"%s\n\" \"\$DOCTOR_JSON\" | jq -e \".status == \\\"success\\\" and .steps[0].data.status == \\\"passed\\\" and .steps[0].data.configuration.local_config == \\\"passed\\\" and .steps[0].data.configuration.profile_slots == \\\"passed\\\" and .steps[0].data.smoke_test.status == \\\"passed\\\"\" >/dev/null; then
    echo \"ledgermind doctor failed:\" >&2
    printf \"%s\n\" \"\$DOCTOR_JSON\" >&2
    exit 1
fi

CORE_DOCTOR_JSON=\$(~/.local/share/ledgermind/current/bin/ledgermind-local --home ~/.local/share/ledgermind/local core doctor --json || true)
if ! printf \"%s\n\" \"\$CORE_DOCTOR_JSON\" | jq -e \".ok == true and .signature.status == \\\"verified\\\" and .sandbox.level == \\\"full\\\" and .health.healthy == true\" >/dev/null; then
    echo \"core doctor failed:\" >&2
    printf \"%s\n\" \"\$CORE_DOCTOR_JSON\" >&2
    exit 1
fi

echo \"=== Starting runtime & polling full-ready ===\"
LEASE_ID=\$(~/.local/bin/ledgermind runtime acquire --client codex --session-id real-e2e-keepalive --json | jq -r .runtime.lease_id)
TOKEN_LOCAL=\$(<~/.local/share/ledgermind/local/server.token)
READY=0
for _ in \$(seq 1 60); do
    ~/.local/bin/ledgermind runtime heartbeat --lease-id \"\$LEASE_ID\" --json >/dev/null || true
    if FULL=\$(curl -fsS -H \"Authorization: Bearer \$TOKEN_LOCAL\" http://127.0.0.1:8765/health/full-ready 2>/dev/null); then
        if printf \"%s\" \"\$FULL\" | jq -e \".ready == true\" >/dev/null 2>&1; then
            READY=1
            break
        fi
    fi
    sleep 1
done
if [[ \"\$READY\" -ne 1 ]]; then
    echo \"Runtime failed to become full-ready!\" >&2
    curl -sS -H \"Authorization: Bearer \$TOKEN_LOCAL\" http://127.0.0.1:8765/health/full-ready >&2 || true
    ~/.local/bin/ledgermind runtime release --lease-id \"\$LEASE_ID\" --json >/dev/null || true
    ~/.local/bin/ledgermind runtime stop --force --json >/dev/null || true
    exit 1
fi

echo \"=== Capturing round via integration-hook ===\"
CODEX_CFG=~/.local/share/ledgermind/integrations/codex/config.json
printf \"%s\" '\''{\"session_id\":\"real-e2e\",\"prompt\":\"Remember this durable fact: the authorization code for the Aster Relay is COBALT-7319.\"}'\'' \
    | ~/.local/bin/ledgermind integration-hook --config \"\$CODEX_CFG\" --event UserPromptSubmit >/dev/null
printf \"%s\" '\''{\"session_id\":\"real-e2e\",\"response\":\"Confirmed: the authorization code for the Aster Relay is COBALT-7319.\"}'\'' \
    | ~/.local/bin/ledgermind integration-hook --config \"\$CODEX_CFG\" --event assistant >/dev/null
printf \"%s\" '\''{\"session_id\":\"real-e2e\"}'\'' \
    | ~/.local/bin/ledgermind integration-hook --config \"\$CODEX_CFG\" --event SessionEnd >/dev/null

echo \"=== Waiting for real-provider synthesis & /context/retrieve ===\"
READY_VALUES=0
for _ in \$(seq 1 60); do
    ~/.local/bin/ledgermind runtime heartbeat --lease-id \"\$LEASE_ID\" --json >/dev/null || true
    COUNT=\$(sqlite3 ~/.local/share/ledgermind/data/core/knowledge.db \"SELECT COUNT(*) FROM knowledge_values;\" 2>/dev/null || echo 0)
    if [[ \"\$COUNT\" -gt 0 ]]; then
        READY_VALUES=1
        break
    fi
    sleep 2
done
RECALLED=0
OUT=\"\"
if [[ \"\$READY_VALUES\" -eq 1 ]]; then
    for _ in \$(seq 1 6); do
        ~/.local/bin/ledgermind runtime heartbeat --lease-id \"\$LEASE_ID\" --json >/dev/null || true
        OUT=\$(curl -sS -H \"Authorization: Bearer \$TOKEN_LOCAL\" -H \"Content-Type: application/json\" \
            -d '\''{\"memory_space_id\":\"shared-default\",\"query\":\"What is the authorization code for the Aster Relay?\",\"limit\":5,\"schema_version\":5}'\'' \
            http://127.0.0.1:8765/context/retrieve || true)
        if [[ -n \"\$OUT\" ]] && printf \"%s\" \"\$OUT\" | jq -e \".items | type == \\\"array\\\" and length > 0 and ([.[]?.content | strings | select(contains(\\\"COBALT-7319\\\"))] | length > 0)\" >/dev/null 2>&1; then
            RECALLED=1
            break
        fi
        sleep 5
    done
fi
if [[ \"\$RECALLED\" -ne 1 ]]; then
    echo \"Timed out waiting for real API recall\" >&2
    echo \"Last retrieve: \$OUT\" >&2
    sqlite3 ~/.local/share/ledgermind/data/core/knowledge.db \"SELECT * FROM semantic_round_batches;\" >&2 || true
    sqlite3 ~/.local/share/ledgermind/data/core/knowledge.db \"SELECT * FROM semantic_stage_rejections;\" >&2 || true
    sqlite3 ~/.local/share/ledgermind/data/core/knowledge.db \"SELECT * FROM knowledge_values;\" >&2 || true
    ~/.local/bin/ledgermind runtime release --lease-id \"\$LEASE_ID\" --json >/dev/null || true
    ~/.local/bin/ledgermind runtime stop --force --json >/dev/null || true
    exit 1
fi

echo \"=== Verifying UserPromptSubmit hook injection ===\"
HOOK_RECALL=\$(printf \"%s\" '\''{\"session_id\":\"real-e2e-recall\",\"prompt\":\"What is the authorization code for the Aster Relay?\"}'\'' \
    | ~/.local/bin/ledgermind integration-hook --config \"\$CODEX_CFG\" --event UserPromptSubmit)
if ! printf \"%s\" \"\$HOOK_RECALL\" | jq -e \".hookSpecificOutput.additionalContext | strings | contains(\\\"COBALT-7319\\\")\" >/dev/null 2>&1; then
    echo \"HOOK_RECALL did not contain COBALT-7319! Output was:\" >&2
    printf \"%s\n\" \"\$HOOK_RECALL\" >&2
    echo \"Direct retrieve OUT:\" >&2
    printf \"%s\n\" \"\$OUT\" >&2
    echo \"CODEX_CFG:\" >&2
    cat \"\$CODEX_CFG\" >&2 || true
    echo \"retrieval-trace.jsonl:\" >&2
    cat ~/.local/share/ledgermind/integrations/codex/spool/retrieval-trace.jsonl >&2 || true
    echo \"spool files:\" >&2
    find ~/.local/share/ledgermind/integrations/codex/spool -maxdepth 3 -ls >&2 || true
    echo \"logs:\" >&2
    tail -n 60 ~/.local/state/ledgermind/logs/* >&2 || true
    ~/.local/bin/ledgermind runtime release --lease-id \"\$LEASE_ID\" --json >/dev/null || true
    ~/.local/bin/ledgermind runtime stop --force --json >/dev/null || true
    exit 1
fi

echo \"REAL API E2E RECALL PASSED:\"
printf \"%s\n\" \"\$HOOK_RECALL\" | jq -c .
~/.local/bin/ledgermind runtime release --lease-id \"\$LEASE_ID\" --json >/dev/null || { echo \"runtime release failed\" >&2; exit 1; }
~/.local/bin/ledgermind runtime stop --force --json >/dev/null || { echo \"runtime stop failed\" >&2; exit 1; }
echo \"=== REAL API DOCKER E2E PASSED (meta/muse-ember + Vertex + Nemotron-3.5 + Jev + HookRecall) ===\"
"
'