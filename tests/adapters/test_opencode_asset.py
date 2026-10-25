from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _asset() -> str:
    return (
        Path(__file__).parents[2]
        / "src"
        / "ledgermind_integrations"
        / "adapters"
        / "opencode"
        / "ledgermind.js"
    ).read_text(encoding="utf-8")


def test_opencode_injection_is_persisted_once_in_message_parts() -> None:
    asset = _asset()

    assert '"experimental.chat.system.transform"' not in asset
    assert 'firstTextPart.text += ' in asset
    assert 'event.type === "session.compacted"' in asset
    assert 'bridge("Stop", { session_id: sessionID, cwd: directory })' in asset
    assert 'bridge("SessionEnd", { session_id: sessionID, cwd: directory })' not in asset


def test_opencode_asset_exports_dual_api_definition() -> None:
    asset = _asset()

    assert "export default {" in asset
    assert 'id: "ledgermind"' in asset
    assert "server: LedgerMindPlugin" in asset
    assert "async setup(ctx)" in asset
    assert 'await ctx.session.hook("prompt"' in asset
    assert 'await ctx.session.hook("context"' in asset
    assert 'await ctx.tool.hook("execute.before"' in asset
    assert 'await ctx.tool.hook("execute.after"' in asset
    assert "ctx.event.subscribe" in asset
    assert 'event.type === "session.execution.started"' in asset
    assert 'event.type === "session.text.ended"' in asset
    assert 'event.type === "session.compaction.ended"' in asset
    assert 'event.type === "session.deleted"' in asset


def _materialized(tmp_path: Path) -> Path:
    bridge = tmp_path / "bridge"
    bridge.write_text(
        "#!/bin/sh\n"
        "event=\"$5\"\n"
        "payload=$(cat)\n"
        f"log={json.dumps(str(tmp_path / 'calls.tsv'))}\n"
        "printf '%s\\t%s\\n' \"$event\" \"$payload\" >> \"$log\"\n"
        "if [ \"$event\" = \"UserPromptSubmit\" ]; then\n"
        "  printf '%s' '{\"hookSpecificOutput\":{\"additionalContext\":\"MEMORY\"}}'\n"
        "else\n"
        "  printf '%s' '{}'\n"
        "fi\n",
        encoding="utf-8",
    )
    bridge.chmod(0o700)
    module = tmp_path / "ledgermind.mjs"
    module.write_text(
        _asset()
        .replace('"__LEDGERMIND_COMMAND__"', json.dumps(str(bridge)))
        .replace('"__LEDGERMIND_CONFIG__"', json.dumps(str(tmp_path / "config.json"))),
        encoding="utf-8",
    )
    return module


def test_opencode_context_is_persisted_without_repeated_system_injection(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for the OpenCode adapter contract test")

    _materialized(tmp_path)
    runner = tmp_path / "runner.mjs"
    runner.write_text(
        "import { LedgerMindPlugin } from './ledgermind.mjs'\n"
        "const plugin = await LedgerMindPlugin({ directory: '/workspace' })\n"
        "const parts = [{ type: 'text', text: 'USER' }]\n"
        "await plugin['chat.message']({ sessionID: 's1' }, { parts })\n"
        "await plugin.event({ event: { type: 'session.idle', properties: { sessionID: 's1' } } })\n"
        "console.log(JSON.stringify({ parts }))\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [node, str(runner)],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    observed = json.loads(result.stdout)
    assert observed == {"parts": [{"type": "text", "text": "USER\n\nMEMORY"}]}


def test_opencode_setup_bridges_hooks_and_events(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for the OpenCode adapter contract test")

    _materialized(tmp_path)
    call_log = tmp_path / "calls.tsv"
    runner = tmp_path / "runner.mjs"
    runner.write_text(
        "import plugin, { LedgerMindPlugin } from './ledgermind.mjs'\n"
        "import { existsSync, readFileSync } from 'node:fs'\n"
        "\n"
        "const logPath = __CALLS_LOG__\n"
        "const hooks = {}\n"
        "const queue = []\n"
        "const controller = new AbortController()\n"
        "async function* subscribe(options) {\n"
        "  const signal = options.signal\n"
        "  while (!signal.aborted) {\n"
        "    if (queue.length) {\n"
        "      yield queue.shift()\n"
        "      continue\n"
        "    }\n"
        "    await new Promise((resolve) => setTimeout(resolve, 5))\n"
        "  }\n"
        "}\n"
        "const ctx = {\n"
        "  location: { directory: '/workspace' },\n"
        "  session: { hook: async (name, fn) => { hooks[name] = fn } },\n"
        "  tool: { hook: async (name, fn) => { hooks[name] = fn } },\n"
        "  event: { subscribe },\n"
        "}\n"
        "const cleanup = await plugin.setup(ctx)\n"
        "await hooks.prompt({ sessionID: 's1', prompt: { text: 'USER' } })\n"
        "const system = []\n"
        "await hooks.context({ sessionID: 's1', system })\n"
        "await hooks['execute.before']({\n"
        "  sessionID: 's1',\n"
        "  tool: 'bash',\n"
        "  id: 't1',\n"
        "  input: { cmd: 'pwd' },\n"
        "})\n"
        "await hooks['execute.after']({\n"
        "  sessionID: 's1',\n"
        "  tool: 'bash',\n"
        "  id: 't1',\n"
        "  status: 'completed',\n"
        "  result: { output: 'ok' },\n"
        "})\n"
        "const push = (event) => queue.push(event)\n"
        "push({ type: 'session.execution.started', data: { sessionID: 's1' } })\n"
        "push({ type: 'session.text.ended', data: {\n"
        "  sessionID: 's1', assistantMessageID: 'm1', ordinal: 0, text: 'Hello',\n"
        "} })\n"
        "push({ type: 'session.text.ended', data: {\n"
        "  sessionID: 's1', assistantMessageID: 'm1', ordinal: 1, text: 'World',\n"
        "} })\n"
        "push({ type: 'session.execution.succeeded', data: { sessionID: 's1' } })\n"
        "push({ type: 'session.idle', data: { sessionID: 's1' } })\n"
        "push({ type: 'session.compaction.ended', data: { sessionID: 's1' } })\n"
        "push({ type: 'session.deleted', data: { sessionID: 's1' } })\n"
        "const deadline = Date.now() + 4000\n"
        "while (Date.now() < deadline) {\n"
        "  const text = existsSync(logPath) ? readFileSync(logPath, 'utf8') : ''\n"
        "  if (text.includes('SessionReset')) break\n"
        "  await new Promise((resolve) => setTimeout(resolve, 20))\n"
        "}\n"
        "cleanup()\n"
        "const log = existsSync(logPath) ? readFileSync(logPath, 'utf8') : ''\n"
        "console.log(JSON.stringify({\n"
        "  system,\n"
        "  log,\n"
        "  meta: {\n"
        "    id: plugin.id,\n"
        "    server: typeof plugin.server,\n"
        "    named: typeof LedgerMindPlugin,\n"
        "    same: LedgerMindPlugin === plugin.server,\n"
        "  },\n"
        "}))\n".replace("__CALLS_LOG__", json.dumps(str(call_log))),
        encoding="utf-8",
    )

    result = subprocess.run(
        [node, str(runner)],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    observed = json.loads(result.stdout)
    assert observed["system"] == [{"type": "text", "text": "MEMORY"}]
    assert observed["meta"] == {
        "id": "ledgermind",
        "server": "function",
        "named": "function",
        "same": True,
    }

    calls = [line.split("\t", 1) for line in observed["log"].splitlines()]
    events = [event for event, _ in calls]
    assert events == [
        "UserPromptSubmit",
        "PreToolUse",
        "PostToolUse",
        "assistant",
        "Stop",
        "PostCompact",
        "SessionReset",
    ]
    payloads = [json.loads(payload) for _, payload in calls]
    assert payloads[0] == {"session_id": "s1", "cwd": "/workspace", "prompt": "USER"}
    assert payloads[1] == {
        "session_id": "s1",
        "cwd": "/workspace",
        "tool_name": "bash",
        "tool_use_id": "t1",
        "tool_input": {"cmd": "pwd"},
    }
    assert payloads[2] == {
        "session_id": "s1",
        "cwd": "/workspace",
        "tool_name": "bash",
        "tool_use_id": "t1",
        "tool_response": {"output": "ok"},
    }
    assert payloads[3] == {"session_id": "s1", "response": "Hello\nWorld"}
    assert payloads[4] == {"session_id": "s1", "cwd": "/workspace"}
    assert payloads[5] == {"session_id": "s1", "cwd": "/workspace"}
    assert payloads[6] == {"session_id": "s1", "cwd": "/workspace"}
