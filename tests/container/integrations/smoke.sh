#!/usr/bin/env bash
set -euo pipefail

artifact_root=${LEDGERMIND_SMOKE_ARTIFACT_ROOT:-/artifacts}
installer_source="$artifact_root/ledgermind-installer-linux-x86_64"
manifest="$artifact_root/install-manifest.json"
manifest_signature="$artifact_root/install-manifest.sig"
bundle="$artifact_root/ledgermind-linux-x86_64.tar.zst"
report_root=${LEDGERMIND_SMOKE_REPORT_ROOT:-/reports}

mkdir -p "$report_root"

for required in "$installer_source" "$manifest" "$manifest_signature" "$bundle"; do
    if [[ ! -f "$required" ]]; then
        printf 'missing smoke artifact: %s\n' "$required" >&2
        exit 2
    fi
done

installer=/tmp/ledgermind-installer
cp "$installer_source" "$installer"
chmod 700 "$installer"

cat > /tmp/ledgermind-smoke-install.json <<'JSON'
{
  "schema_version": 2,
  "semantic_language": "en",
  "generation": {
    "endpoint": "http://127.0.0.1:65534",
    "token_env": "LEDGERMIND_SMOKE_GENERATION_TOKEN",
    "model": "smoke-generation",
    "object_resolution_model": "smoke-generation"
  },
  "embedding": {
    "mode": "api",
    "api": {
      "endpoint": "http://127.0.0.1:65534",
      "token_env": "LEDGERMIND_SMOKE_EMBEDDING_TOKEN",
      "model": "smoke-embedding",
      "dimensions": 3
    }
  },
  "integrations": []
}
JSON
chmod 600 /tmp/ledgermind-smoke-install.json

export LEDGERMIND_SMOKE_GENERATION_TOKEN=container-smoke-only
export LEDGERMIND_SMOKE_EMBEDDING_TOKEN=container-smoke-only

{
    hermes --version
    codex --version
    claude --version
    cursor-agent --version
    opencode --version
    openclaw --version
} > "$report_root/agent-versions.txt"

"$installer" install \
    --non-interactive \
    --config /tmp/ledgermind-smoke-install.json \
    --json \
    --manifest "$manifest" \
    --manifest-signature "$manifest_signature" \
    --bundle "$bundle" \
    --skip-provider-probe > "$report_root/install.json"

ledgermind_bin="$HOME/.local/bin/ledgermind"
"$ledgermind_bin" integrations discover --json > "$report_root/discovery.json"

jq -e '
  .steps[0].data.integrations as $i |
  ($i.hermes.detected == true) and
  ($i.codex.detected == true) and
  ($i["claude-code"].detected == true) and
  ($i.cursor.detected == true) and
  ($i.opencode.detected == true) and
  ($i.openclaw.detected == true)
' "$report_root/discovery.json" >/dev/null

for target in hermes codex claude-code cursor opencode openclaw; do
    "$ledgermind_bin" integrations connect "$target" --json \
        > "$report_root/connect-$target.json"
done

"$ledgermind_bin" integrations status --json > "$report_root/status.json"
jq -e '
  .steps[0].data.integrations as $i |
  ($i.hermes.connected == true) and
  ($i.codex.connected == true) and
  ($i["claude-code"].connected == true) and
  ($i.cursor.connected == true) and
  ($i.opencode.connected == true) and
  ($i.openclaw.connected == true)
' "$report_root/status.json" >/dev/null

for target in codex claude-code cursor; do
    config="$HOME/.local/share/ledgermind/integrations/$target/config.json"
    printf '%s' '{"session_id":"container-smoke","prompt":"Recall the rollout procedure"}' |
        timeout 20s "$ledgermind_bin" integration-hook \
            --config "$config" --event UserPromptSubmit \
            > "$report_root/hook-$target.json"
    printf '%s' '{"session_id":"container-smoke"}' |
        timeout 20s "$ledgermind_bin" integration-hook \
            --config "$config" --event SessionEnd \
            > "$report_root/session-end-$target.json"
done

node --check "$OPENCODE_CONFIG_DIR/plugins/ledgermind.js"
node --check "$HOME/.openclaw/extensions/ledgermind-memory/index.js"
hermes plugins doctor --ci "$HERMES_HOME/plugins/ledgermind-hermes" \
    > "$report_root/hermes-plugin-doctor.txt"
openclaw plugins inspect ledgermind-memory --runtime --json \
    > "$report_root/openclaw-plugin-inspect.json"
jq -e '
  (.plugin.id == "ledgermind-memory") and
  (.plugin.status == "loaded") and
  (.plugin.enabled == true) and
  (.plugin.imported == true) and
  (.plugin.hookCount == 5) and
  (.shape == "hook-only") and
  ([.diagnostics[]? | select(.level == "error" or .level == "warn")] | length == 0)
' "$report_root/openclaw-plugin-inspect.json" >/dev/null
openclaw plugins doctor > "$report_root/openclaw-plugin-doctor.txt"
"$ledgermind_bin" runtime status --json > "$report_root/runtime-status.json"
jq -e '(.runtime.active_leases | length) == 0' \
    "$report_root/runtime-status.json" >/dev/null
"$ledgermind_bin" runtime stop --force --json > "$report_root/runtime-stop.json"
"$ledgermind_bin" runtime status --json > "$report_root/runtime-stopped-status.json"
jq -e '.runtime.running == false and (.runtime.active_leases | length) == 0' \
    "$report_root/runtime-stopped-status.json" >/dev/null

printf '%s\n' 'LedgerMind container integration smoke: passed'
