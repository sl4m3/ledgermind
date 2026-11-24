# End-to-End Docker Verification

Runs the complete LedgerMind lifecycle inside a disposable container without modifying the host system:
1. Unit tests and lint checks (`pytest tests/unit/installer/` + `ruff`).
2. Test-signed release assembly combining `v5.0.0` signed `ledgermind-core` with workspace `local` / `integrations` / `protocol`.
3. `install.sh` one-command bootstrap -> Localhost Web UI setup wizard (`127.0.0.1`, token-authenticated) AND terminal `--cli` fallback.
4. Full audit of Core/Local configs (`0600` permissions, `LocalConfig` sync, concurrency, `rounds.db` profile slots) and `ledgermind doctor --json`.
5. Live runtime startup (`full-ready` with `bubblewrap` sandbox), round capture via `integration-hook`, Core processing, and knowledge retrieval (`COBALT-7319`).

## Autonomous E2E (no external API keys)

```bash
./local/tests/container/e2e/run-autonomous-e2e.sh
```

## Real-API E2E (OpenRouter / NVIDIA NIM)

```bash
LEDGERMIND_GENERATION_TOKEN=sk-or-... \
LEDGERMIND_GENERATION_ROUTE=deepseek/fp8 \
  ./local/tests/container/e2e/run-real-api-e2e.sh
```
