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


def test_opencode_context_is_persisted_without_repeated_system_injection(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for the OpenCode adapter contract test")

    bridge = tmp_path / "bridge"
    bridge.write_text(
        "#!/bin/sh\n"
        "printf '%s' '{\"hookSpecificOutput\":{\"additionalContext\":\"MEMORY\"}}'\n",
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
