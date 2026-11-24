from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from ledgermind_local.installer import cli, web_wizard
from ledgermind_local.installer.errors import ProviderProbeError, UserCancelledError
from ledgermind_local.installer.models import (
    EmbeddingApiConfig,
    EmbeddingConfig,
    GenerationConfig,
    InstallerConfig,
)
from ledgermind_local.installer.openrouter import OpenRouterEndpoint
from ledgermind_local.installer.paths import InstallerPaths
from ledgermind_local.installer.targets.base import BaseTargetAdapter, TargetDiscovery


def _api_payload() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "semantic_language": "en",
        "memory_mode": "shared",
        "integrations": [],
        "generation": {
            "provider_profile": "openai_compatible",
            "endpoint": "https://provider.example/v1",
            "model": "model-1",
            "token": "gen-secret",
            "max_concurrency": 3,
        },
        "resolution_decision": {
            "backend": "jev",
            "token": "jev-secret",
        },
        "embedding": {
            "mode": "api",
            "api": {
                "endpoint": "https://provider.example/v1",
                "model": "embed-1",
                "dimensions": 64,
                "token": "emb-secret",
                "concurrency": 2,
            },
        },
    }


def _http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    payload: object | None = None,
) -> tuple[int, dict[str, Any]]:
    body = (
        json.dumps(payload).encode("utf-8")
        if payload is not None
        else None
    )
    req_headers = dict(headers or {})
    if body is not None:
        req_headers.setdefault("Content-Type", "application/json")
    request = Request(url, data=body, headers=req_headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_should_use_web_ui_respects_flags_and_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LEDGERMIND_INSTALLER_UI", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.delenv("SSH_CLIENT", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)

    assert (
        web_wizard.should_use_web_ui(
            "web", json_output=False, non_interactive=False
        )
        is True
    )
    assert (
        web_wizard.should_use_web_ui(
            "cli", json_output=False, non_interactive=False
        )
        is False
    )
    assert (
        web_wizard.should_use_web_ui(
            "web", json_output=True, non_interactive=False
        )
        is False
    )
    assert (
        web_wizard.should_use_web_ui(
            "web", json_output=False, non_interactive=True
        )
        is False
    )

    monkeypatch.setattr(web_wizard.sys.stderr, "isatty", lambda: True)
    assert (
        web_wizard.should_use_web_ui(
            "auto", json_output=False, non_interactive=False
        )
        is True
    )

    monkeypatch.setenv("SSH_TTY", "/dev/pts/1")
    assert (
        web_wizard.should_use_web_ui(
            "auto", json_output=False, non_interactive=False
        )
        is False
    )

    monkeypatch.setenv("LEDGERMIND_INSTALLER_UI", "web")
    assert (
        web_wizard.should_use_web_ui(
            "auto", json_output=False, non_interactive=False
        )
        is True
    )


def test_web_wizard_enforces_token_and_completes_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeAdapter(BaseTargetAdapter):
        id = "codex"
        label = "Codex CLI"

        def discover(self) -> TargetDiscovery:
            return TargetDiscovery("codex", "Codex CLI", True, home=tmp_path)

        def preflight(self, context: Any) -> dict[str, Any]:
            return {}

        def install(self, context: Any) -> dict[str, Any]:
            return {}

        def configure(self, context: Any) -> dict[str, Any]:
            return {}

        def register_hooks(self, context: Any) -> dict[str, Any]:
            return {}

        def verify(self, context: Any) -> dict[str, Any]:
            return {}

        def repair(self, context: Any) -> dict[str, Any]:
            return {}

        def uninstall(self, context: Any, *, purge: bool = False) -> dict[str, Any]:
            return {}

    monkeypatch.setattr(web_wizard, "target_ids", lambda: ("codex",))
    monkeypatch.setattr(web_wizard, "get_target_adapter", lambda _id: FakeAdapter())

    captured: dict[str, Any] = {}

    def fake_install(
        config: InstallerConfig, progress: Any
    ) -> dict[str, Any]:
        progress("providers", "Checking providers")
        progress("complete", "Done")
        captured["config"] = config
        return {"status": "success", "readiness": {"core": "passed"}}

    server, url, state = web_wizard.start_web_wizard_server(
        install_callback=fake_install,
        preflight_home=tmp_path,
        openrouter_endpoint_loader=lambda model, _tok: (
            OpenRouterEndpoint(
                route="provider-a/fp8",
                provider="Provider A",
                quantization="fp8",
                context_length=131072,
                prompt_price="0.000001",
                completion_price="0.000002",
                supported_parameters=("structured_outputs", "response_format"),
            ),
        ),
        embedding_dimension_loader=lambda _cfg, _tok: 2048,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url, token = url.split("/?token=")
        headers = {"X-LedgerMind-Setup-Token": token}

        with pytest.raises(HTTPError) as missing_tok:
            urlopen(base_url + "/", timeout=5)
        assert missing_tok.value.code == 403

        status_code, _ = _http_json(base_url + "/api/preflight")
        assert status_code == 401

        with urlopen(url, timeout=5) as page_resp:
            html = page_resp.read().decode("utf-8")
        assert token in html
        assert "LedgerMind Setup" in html

        code, preflight = _http_json(base_url + "/api/preflight", headers=headers)
        assert code == 200
        assert preflight["agents"][0]["id"] == "codex"
        assert preflight["agents"][0]["detected"] is True

        code, routes = _http_json(
            base_url + "/api/openrouter/endpoints",
            method="POST",
            headers=headers,
            payload={"model": "deepseek/deepseek-v4-flash-0731", "token": "or-key"},
        )
        assert code == 200
        assert routes["endpoints"][0]["route"] == "provider-a/fp8"

        code, dims = _http_json(
            base_url + "/api/embedding/dimensions",
            method="POST",
            headers=headers,
            payload={
                "endpoint": "https://provider.example/v1",
                "model": "embed-1",
                "token": "emb-secret",
            },
        )
        assert code == 200
        assert dims["dimensions"] == 2048

        code, accepted = _http_json(
            base_url + "/api/install",
            method="POST",
            headers=headers,
            payload=_api_payload(),
        )
        assert code == 202
        assert accepted["status"] == "running"

        final_status: dict[str, Any] = {}
        for _ in range(40):
            _, final_status = _http_json(base_url + "/api/status", headers=headers)
            if final_status.get("status") in {"success", "failed"}:
                break
            time.sleep(0.05)

        assert final_status["status"] == "success"
        assert final_status["result"]["readiness"]["core"] == "passed"
        assert captured["config"].generation.max_concurrency == 3
        assert captured["config"].embedding.api is not None
        assert captured["config"].embedding.api.concurrency == 2

        code, closing = _http_json(
            base_url + "/api/shutdown",
            method="POST",
            headers=headers,
            payload={"action": "finish"},
        )
        assert code == 200
        assert closing["status"] == "closing"
        assert state.done_event.is_set()
        assert state.cancelled is False
    finally:
        server.shutdown()
        server.server_close()


def test_web_wizard_allows_retry_after_provider_failure(tmp_path: Path) -> None:
    attempts = 0

    def flaky_install(
        config: InstallerConfig, progress: Any
    ) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        progress("providers", "Checking providers")
        if attempts == 1:
            raise ProviderProbeError("bad API key")
        return {"status": "success", "model": config.generation.model}

    server, url, state = web_wizard.start_web_wizard_server(
        install_callback=flaky_install,
        preflight_home=tmp_path,
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base_url, token = url.split("/?token=")
        headers = {"X-LedgerMind-Setup-Token": token}
        _http_json(
            base_url + "/api/install",
            method="POST",
            headers=headers,
            payload=_api_payload(),
        )
        for _ in range(40):
            _, st = _http_json(base_url + "/api/status", headers=headers)
            if st["status"] == "failed":
                break
            time.sleep(0.05)
        assert st["status"] == "failed"
        assert "bad API key" in st["error"]

        code, _ = _http_json(
            base_url + "/api/install",
            method="POST",
            headers=headers,
            payload=_api_payload(),
        )
        assert code == 202
        for _ in range(40):
            _, st = _http_json(base_url + "/api/status", headers=headers)
            if st["status"] == "success":
                break
            time.sleep(0.05)
        assert st["status"] == "success"
        assert attempts == 2
    finally:
        state.done_event.set()
        server.shutdown()
        server.server_close()


def test_web_wizard_cancel_raises_user_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cli,
        "_paths",
        lambda _args: InstallerPaths(home_override=tmp_path / "install-home"),
    )

    def fake_run_web_install(**_kwargs: Any) -> dict[str, Any]:
        raise UserCancelledError("installation cancelled by user")

    monkeypatch.setattr(web_wizard, "run_web_install", fake_run_web_install)
    exit_code = cli.main(["install", "--web", "--no-browser"])
    assert exit_code == 15


def test_cli_routes_to_web_or_cli_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        cli,
        "_paths",
        lambda _args: InstallerPaths(home_override=tmp_path / "install-home"),
    )

    def fake_run_web_install(**kwargs: Any) -> dict[str, Any]:
        seen.append("web")
        assert kwargs["open_browser"] is False
        assert kwargs["port"] == 18777
        return {"status": "success"}

    monkeypatch.setattr(web_wizard, "run_web_install", fake_run_web_install)
    assert cli.main(["--web", "--no-browser", "--web-port", "18777"]) == 0
    assert seen == ["web"]

    monkeypatch.setattr(
        cli,
        "_config",
        lambda _args: (
            InstallerConfig(
                semantic_language="en",
                generation=GenerationConfig(
                    endpoint="https://provider.example/v1",
                    token="secret",
                    model="model-1",
                ),
                embedding=EmbeddingConfig(
                    mode="api",
                    api=EmbeddingApiConfig(
                        endpoint="https://provider.example/v1",
                        token="secret",
                        model="embed-1",
                        dimensions=64,
                    ),
                ),
            ),
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        cli,
        "install",
        lambda **_kwargs: seen.append("cli") or {"status": "success"},
    )
    assert cli.main(["install", "--cli"]) == 0
    assert seen == ["web", "cli"]
