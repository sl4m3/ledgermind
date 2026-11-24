#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../../.." && pwd)"
ARTIFACTS_DIR="${LEDGERMIND_V5_ARTIFACTS:-/tmp/ledgermind-v5-artifacts}"

for required in \
    "$ARTIFACTS_DIR/install-manifest.json" \
    "$ARTIFACTS_DIR/ledgermind-linux-x86_64.tar.zst" \
    "$ARTIFACTS_DIR/ledgermind_inference-0.1.0-cp310-abi3-linux_x86_64.whl"
do
    if [[ ! -f "$required" ]]; then
        printf 'Missing required v5.0.0 artifact: %s\n' "$required" >&2
        exit 2
    fi
done

docker build -t ledgermind-e2e -f "${SCRIPT_DIR}/Dockerfile" "${SCRIPT_DIR}"

docker run --rm \
    --security-opt seccomp=unconfined \
    --security-opt apparmor=unconfined \
    -v "${REPO_ROOT}:/workspace:ro" \
    -v "${ARTIFACTS_DIR}:/artifacts:ro" \
    ledgermind-e2e bash -lc '
set -euo pipefail

echo "=== 1. Unit tests & lint ==="
cp -r /workspace/protocol/python /tmp/proto
cp -r /workspace/integrations /tmp/integ
cp -r /workspace/local /tmp/local_pkg
pip install -q --no-deps /tmp/proto /artifacts/ledgermind_inference-0.1.0-cp310-abi3-linux_x86_64.whl /tmp/integ /tmp/local_pkg
(cd /tmp/local_pkg && pytest tests/unit/installer/ -q)
(cd /tmp/local_pkg && ruff check src/ledgermind_local/bootstrap.py src/ledgermind_local/installer/web_wizard.py src/ledgermind_local/installer/cli.py src/ledgermind_local/installer/config_writer.py src/ledgermind_local/installer/models.py src/ledgermind_local/installer/openrouter.py src/ledgermind_local/installer/provider_profiles.py src/ledgermind_local/installer/profiles/generation.py src/ledgermind_local/installer/profiles/probes.py src/ledgermind_local/installer/operations/common.py src/ledgermind_local/installer/operations/configure.py src/ledgermind_local/installer/operations/doctor.py src/ledgermind_local/installer/operations/import_config.py src/ledgermind_local/installer/operations/install.py src/ledgermind_local/installer/operations/repair.py tests/unit/installer/test_web_wizard.py tests/unit/installer/test_install_experience.py tests/unit/installer/test_provider_probes.py tests/unit/installer/test_openrouter_discovery.py tests/unit/installer/test_embedding_identity.py tests/unit/installer/test_model_defaults.py)
cmp -s /workspace/local/scripts/install.sh /workspace/local/install.sh

echo "=== 2. Prepare TLS trust & build test-signed release (v5.0.0 Core + workspace Local/WebUI) ==="
mkdir -p /tmp/certs
openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout /tmp/certs/openrouter.key \
    -out /tmp/certs/openrouter.crt \
    -days 2 \
    -subj "/CN=openrouter.ai" \
    -addext "subjectAltName=DNS:openrouter.ai" >/dev/null 2>&1
cp /tmp/certs/openrouter.crt /usr/local/share/ca-certificates/mock-openrouter.crt
update-ca-certificates >/dev/null
CERTIFI_CA=$(python3 -c "import certifi; print(certifi.where())")
cat /tmp/certs/openrouter.crt >> "$CERTIFI_CA"
echo "127.0.0.1 openrouter.ai" >> /etc/hosts

python3 /workspace/local/tests/container/e2e/build_test_release.py \
    --artifacts /artifacts \
    --workspace /workspace \
    --output /tmp/test-release \
    --extra-ca-cert /tmp/certs/openrouter.crt

echo "=== 3. Start local TLS + HTTP mock inference & release HTTP server ==="

python3 /workspace/local/tests/container/e2e/mock_inference_server.py \
    --http-port 18080 \
    --https-port 443 \
    --cert /tmp/certs/openrouter.crt \
    --key /tmp/certs/openrouter.key \
    --dimensions 64 \
    --log /tmp/mock-inference-requests.jsonl &
MOCK_PID=$!

python3 -m http.server 18090 --bind 127.0.0.1 --directory /tmp/test-release >/dev/null 2>&1 &
REL_PID=$!
trap "kill $MOCK_PID $REL_PID 2>/dev/null || true" EXIT

sleep 1
curl -fsS http://127.0.0.1:18090/install-manifest.json >/dev/null

echo "=== 4. Test 1-command install.sh -> Web UI wizard (non-root user e2e) ==="
PUB_B64=$(cat /tmp/test-release/public_key.b64)
su - e2e -c "
set -euo pipefail
mkdir -p ~/.codex ~/.claude
export LEDGERMIND_RELEASE_BASE_URL=\"http://127.0.0.1:18090\"
export LEDGERMIND_INSTALLER_PUBLIC_KEY=\"${PUB_B64}\"
export LEDGERMIND_INSTALLER_UI=web

sh /tmp/test-release/install.sh --web --web-port 18765 --no-browser > /tmp/web-install.log 2>&1 &
INST_PID=\$!

URL=\"\"
for _ in \$(seq 1 60); do
    if grep -q \"http://127.0.0.1:18765/?token=\" /tmp/web-install.log 2>/dev/null; then
        URL=\$(grep -oE \"http://127\\.0\\.0\\.1:18765/\\?token=[A-Za-z0-9_-]+\" /tmp/web-install.log | head -n1)
        break
    fi
    sleep 0.25
done
test -n \"\$URL\"
TOKEN=\"\${URL#*token=}\"
BASE=\"http://127.0.0.1:18765\"

curl -fsS \"\$URL\" | grep -q \"LedgerMind Setup\"
curl -fsS -H \"X-LedgerMind-Setup-Token: \$TOKEN\" \"\$BASE/api/preflight\" | jq -e \".preflight.bubblewrap == true and ([.agents[] | select(.detected == true)] | length) >= 2\" >/dev/null

DIMS=\$(curl -fsS -X POST -H \"X-LedgerMind-Setup-Token: \$TOKEN\" -H \"Content-Type: application/json\" \
    -d '\''{\"endpoint\":\"http://127.0.0.1:18080/v1\",\"model\":\"mock-embed\",\"token\":\"mock-emb-key\"}'\'' \
    \"\$BASE/api/embedding/dimensions\" | jq -r .dimensions)
test \"\$DIMS\" -eq 64

cat > /tmp/web-payload.json <<\"JSON\"
{
  \"schema_version\": 2,
  \"semantic_language\": \"en\",
  \"memory_mode\": \"shared\",
  \"integrations\": [
    {\"id\": \"codex\", \"enabled\": true},
    {\"id\": \"claude-code\", \"enabled\": true}
  ],
  \"generation\": {
    \"provider_profile\": \"openai_compatible\",
    \"endpoint\": \"http://127.0.0.1:18080/v1\",
    \"model\": \"mock-gen-120b\",
    \"token\": \"mock-gen-key\",
    \"max_concurrency\": 4
  },
  \"resolution_decision\": {
    \"backend\": \"jev\",
    \"token\": \"mock-jev-key\"
  },
  \"embedding\": {
    \"mode\": \"api\",
    \"api\": {
      \"endpoint\": \"http://127.0.0.1:18080/v1\",
      \"model\": \"mock-embed\",
      \"dimensions\": 64,
      \"token\": \"mock-emb-key\",
      \"concurrency\": 3
    }
  },
  \"reranker\": {\"mode\": \"disabled\"},
  \"runtime\": {\"residency_mode\": \"session\"}
}
JSON

curl -fsS -X POST -H \"X-LedgerMind-Setup-Token: \$TOKEN\" -H \"Content-Type: application/json\" \
    -d @/tmp/web-payload.json \"\$BASE/api/install\" >/dev/null

STATUS=\"\"
for _ in \$(seq 1 120); do
    STATUS_JSON=\$(curl -fsS -H \"X-LedgerMind-Setup-Token: \$TOKEN\" \"\$BASE/api/status\")
    STATUS=\$(printf \"%s\" \"\$STATUS_JSON\" | jq -r .status)
    if [[ \"\$STATUS\" == \"success\" || \"\$STATUS\" == \"failed\" ]]; then
        break
    fi
    sleep 0.5
done
if [[ \"\$STATUS\" != \"success\" ]]; then
    echo \"Web install failed:\" >&2
    printf \"%s\n\" \"\$STATUS_JSON\" >&2
    exit 1
fi
curl -fsS -X POST -H \"X-LedgerMind-Setup-Token: \$TOKEN\" -H \"Content-Type: application/json\" \
    -d '\''{\"action\":\"finish\"}'\'' \"\$BASE/api/shutdown\" >/dev/null
wait \$INST_PID

echo \"=== 5. Verify Terminal CLI fallback (--cli) in separate --home ===\"
cat <<\"EOF\" | ~/.local/bin/ledgermind install --cli --home /tmp/cli-home \
    --manifest /tmp/test-release/install-manifest.json \
    --manifest-signature /tmp/test-release/install-manifest.sig \
    --bundle /tmp/test-release/ledgermind-linux-x86_64.tar.zst >/tmp/cli-install.log
1
none
1
3
http://127.0.0.1:18080/v1
mock-gen-key
mock-gen-120b
1
http://127.0.0.1:18080/v1
yes
mock-embed
1
1
mock-jev-key
1
EOF
test -f /tmp/cli-home/.config/ledgermind/local-config.json
test -f /tmp/cli-home/.local/share/ledgermind/local/config.json

echo \"=== 6. Audit all Core & Local configs + ledgermind doctor ===\"
for f in \
    ~/.config/ledgermind/config.json \
    ~/.config/ledgermind/profiles.json \
    ~/.config/ledgermind/local-config.json \
    ~/.config/ledgermind/secrets.json \
    ~/.config/ledgermind/runtime.token \
    ~/.local/share/ledgermind/local/config.json \
    ~/.local/share/ledgermind/local/server.token
do
    test -f \"\$f\" || { echo \"Missing file: \$f\" >&2; exit 1; }
    mode=\$(stat -c \"%a\" \"\$f\")
    test \"\$mode\" = \"600\" || { echo \"Bad mode \$mode on \$f\" >&2; exit 1; }
done
cmp -s ~/.config/ledgermind/local-config.json ~/.local/share/ledgermind/local/config.json || { echo \"local-config.json mismatch\" >&2; exit 1; }
jq -e \".generation_concurrency == 4 and .embedding.max_concurrency == 3 and .core_security.profile == \\\"secure\\\" and .profile_slots.resolution_decision == \\\"resolution-decision\\\"\" \
    ~/.config/ledgermind/local-config.json >/dev/null || { echo \"Invalid local-config fields\" >&2; cat ~/.config/ledgermind/local-config.json >&2; exit 1; }
if grep -q \"mock-gen-key\\|mock-emb-key\\|mock-jev-key\" ~/.config/ledgermind/config.json ~/.config/ledgermind/local-config.json; then
    echo \"Plaintext secret leaked into config JSON!\" >&2
    exit 1
fi

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

echo \"=== 7. Start runtime -> verify full-ready -> ingest round -> retrieve knowledge ===\"
LEASE_JSON=\$(~/.local/bin/ledgermind runtime acquire --client codex --session-id e2e-harness-keepalive --json)
LEASE_ID=\$(printf \"%s\" \"\$LEASE_JSON\" | jq -r .runtime.lease_id)
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
    sleep 0.5
done
if [[ \"\$READY\" -ne 1 ]]; then
    echo \"Runtime failed to become full-ready!\" >&2
    curl -sS -H \"Authorization: Bearer \$TOKEN_LOCAL\" http://127.0.0.1:8765/health/full-ready || true
    exit 1
fi

CODEX_CFG=~/.local/share/ledgermind/integrations/codex/config.json
printf \"%s\" '\''{\"session_id\":\"e2e-session\",\"prompt\":\"Remember this durable fact: the authorization code for the Aster Relay is COBALT-7319.\"}'\'' \
    | ~/.local/bin/ledgermind integration-hook --config \"\$CODEX_CFG\" --event UserPromptSubmit >/dev/null
printf \"%s\" '\''{\"session_id\":\"e2e-session\",\"response\":\"Noted: the Aster Relay authorization code is COBALT-7319.\"}'\'' \
    | ~/.local/bin/ledgermind integration-hook --config \"\$CODEX_CFG\" --event assistant >/dev/null
printf \"%s\" '\''{\"session_id\":\"e2e-session\"}'\'' \
    | ~/.local/bin/ledgermind integration-hook --config \"\$CODEX_CFG\" --event SessionEnd >/dev/null

RECALLED=0
RETRIEVE=""
for _ in \$(seq 1 90); do
    ~/.local/bin/ledgermind runtime heartbeat --lease-id \"\$LEASE_ID\" --json >/dev/null || true
    RETRIEVE=\$(curl -sS -H \"Authorization: Bearer \$TOKEN_LOCAL\" -H \"Content-Type: application/json\" \
        -d '\''{\"memory_space_id\":\"shared-default\",\"query\":\"What is the authorization code for the Aster Relay?\",\"limit\":5,\"schema_version\":5}'\'' \
        http://127.0.0.1:8765/context/retrieve || true)
    if [[ -n \"\$RETRIEVE\" ]] && printf \"%s\" \"\$RETRIEVE\" | jq -e \".items | type == \\\"array\\\" and length > 0 and ([.[]?.content | strings | select(contains(\\\"COBALT-7319\\\"))] | length > 0)\" >/dev/null 2>&1; then
        RECALLED=1
        break
    fi
    sleep 1
done
if [[ \"\$RECALLED\" -ne 1 ]]; then
    echo \"Knowledge was not materialized/recalled within timeout!\" >&2
    echo \"Last retrieve: \$RETRIEVE\" >&2
    find ~/.local/share/ledgermind/integrations/codex/spool -maxdepth 3 -ls >&2 || true
    cat ~/.local/state/ledgermind/logs/* >&2 || true
    sqlite3 ~/.local/share/ledgermind/data/rounds.db \"SELECT raw_round_id, memory_space_id FROM raw_rounds;\" >&2 || true
    sqlite3 ~/.local/share/ledgermind/data/core/knowledge.db \"SELECT * FROM semantic_round_batches;\" >&2 || true
    sqlite3 ~/.local/share/ledgermind/data/core/knowledge.db \"SELECT * FROM semantic_stage_rejections;\" >&2 || true
    sqlite3 ~/.local/share/ledgermind/data/core/knowledge.db \"SELECT * FROM knowledge_values;\" >&2 || true
    tail -n 40 /tmp/mock-inference-requests.jsonl >&2 || true
    exit 1
fi

HOOK_RECALL=\$(printf \"%s\" '\''{\"session_id\":\"e2e-recall-2\",\"prompt\":\"What is the authorization code for the Aster Relay?\"}'\'' \
    | ~/.local/bin/ledgermind integration-hook --config \"\$CODEX_CFG\" --event UserPromptSubmit)
if ! printf \"%s\" \"\$HOOK_RECALL\" | jq -e \".hookSpecificOutput.additionalContext | strings | contains(\\\"COBALT-7319\\\")\" >/dev/null 2>&1; then
    echo \"HOOK_RECALL did not contain COBALT-7319! Output was:\" >&2
    printf \"%s\n\" \"\$HOOK_RECALL\" >&2
    sqlite3 ~/.local/share/ledgermind/data/core/knowledge.db \".tables\" >&2 || true
    sqlite3 ~/.local/share/ledgermind/data/core/knowledge.db \"SELECT * FROM semantic_round_batches;\" >&2 || true
    sqlite3 ~/.local/share/ledgermind/data/core/knowledge.db \"SELECT * FROM knowledge_values;\" >&2 || true
    cat /tmp/mock-inference-requests.jsonl >&2 || true
    curl -sS -H \"Authorization: Bearer \$TOKEN_LOCAL\" -H \"Content-Type: application/json\" \
        -d '\''{\"memory_space_id\":\"shared-default\",\"query\":\"What is the authorization code for the Aster Relay?\",\"limit\":5,\"schema_version\":5}'\'' \
        http://127.0.0.1:8765/context/retrieve >&2 || true
    exit 1
fi

~/.local/bin/ledgermind runtime release --lease-id \"\$LEASE_ID\" --json >/dev/null
~/.local/bin/ledgermind runtime stop --force --json >/dev/null

echo \"=== AUTONOMOUS DOCKER E2E PASSED (WebUI + CLI + CoreConfig + Doctor + FullReady + Recall) ===\"
"
'