#!/usr/bin/env bash
set -euo pipefail

bin="$HOME/.local/bin/ledgermind"
config="$HOME/.local/share/ledgermind/integrations/codex/config.json"
reports="$HOME/e2e-reports"

"$bin" runtime acquire --client e2e-harness --session-id seed-live --json \
    > "$reports/acquire-live.json"
lease=$(jq -r .runtime.lease_id "$reports/acquire-live.json")
for _ in $(seq 1 100); do
    if curl -fsS http://127.0.0.1:8765/health/live >/dev/null 2>&1; then
        break
    fi
    "$bin" runtime heartbeat --lease-id "$lease" --json >/dev/null
    sleep 0.1
done
token=$(<"$HOME/.local/share/ledgermind/local/server.token")
curl -fsS -H "Authorization: Bearer $token" \
    http://127.0.0.1:8765/health/full-ready \
    > "$reports/health-full-ready.json"

printf '%s' \
    '{"session_id":"seed-live","prompt":"Remember this durable fact until I explicitly replace it: the authorization code for the Aster Relay is COBALT-7319."}' \
    | "$bin" integration-hook --config "$config" --event UserPromptSubmit \
    > "$reports/seed-prompt.json"
printf '%s' \
    '{"session_id":"seed-live","response":"Confirmed: the current durable authorization code for the Aster Relay is COBALT-7319."}' \
    | "$bin" integration-hook --config "$config" --event assistant \
    > "$reports/seed-assistant.json"
printf '%s' '{"session_id":"seed-live"}' \
    | "$bin" integration-hook --config "$config" --event SessionEnd \
    > "$reports/seed-end.json"

recall_ready=0
for _ in $(seq 1 180); do
    "$bin" runtime heartbeat --lease-id "$lease" --json >/dev/null || true
    raw_rounds=$(python3 - <<'PY'
import sqlite3

connection = sqlite3.connect("/home/smoke/.local/share/ledgermind/data/rounds.db")
print(connection.execute("select count(*) from raw_rounds").fetchone()[0])
PY
)
    printf '%s\n' "$raw_rounds" > "$reports/seed-counts.txt"
    if [[ "$raw_rounds" -ge 1 ]]; then
        curl -fsS \
            -H "Authorization: Bearer $token" \
            -H 'Content-Type: application/json' \
            -d '{"memory_space_id":"codex-default","query":"What is the authorization code for the Aster Relay?","limit":5}' \
            http://127.0.0.1:8765/context/retrieve \
            > "$reports/direct-recall.json" || true
        if jq -e '[.items[]?.content | select(contains("COBALT-7319"))] | length > 0' \
            "$reports/direct-recall.json" >/dev/null 2>&1; then
            recall_ready=1
            break
        fi
    fi
    sleep 1
done

[[ "$recall_ready" -eq 1 ]]

printf '%s\n' 'seed_and_direct_recall_passed'
