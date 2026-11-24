"""Localhost Web UI setup wizard backed by the strict InstallerConfig schema."""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import sys
import threading
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import parse_qs, urlparse

from ..model_defaults import load_model_defaults
from .errors import UserCancelledError
from .hardware import detect_devices
from .models import EmbeddingApiConfig, InstallerConfig
from .openrouter import OpenRouterEndpoint, list_openrouter_model_endpoints
from .preflight import check_preflight
from .profiles.probes import discover_embedding_dimensions
from .targets.registry import get_target_adapter, target_ids

_TOKEN_HEADER = "X-LedgerMind-Setup-Token"
_MAX_REQUEST_BYTES = 262_144
_RERANKER_FALLBACK_REVISION = "e61197ed45024b0ed8a2d74b80b4d909f1255473"
logger = logging.getLogger(__name__)


def should_use_web_ui(
    ui_mode: str,
    *,
    json_output: bool,
    non_interactive: bool,
) -> bool:
    """Decide whether interactive install should launch the local Web UI."""

    if non_interactive or json_output:
        return False
    mode = ui_mode.strip().lower() or "auto"
    if mode == "auto":
        env_override = os.environ.get("LEDGERMIND_INSTALLER_UI", "").strip().lower()
        if env_override in {"web", "cli"}:
            mode = env_override
    if mode == "cli":
        return False
    if mode == "web":
        return True
    has_display = bool(
        os.environ.get("DISPLAY", "").strip()
        or os.environ.get("WAYLAND_DISPLAY", "").strip()
    )
    is_ssh = bool(
        os.environ.get("SSH_CONNECTION", "").strip()
        or os.environ.get("SSH_CLIENT", "").strip()
        or os.environ.get("SSH_TTY", "").strip()
    )
    interactive_tty = sys.stderr.isatty() or sys.stdin.isatty()
    return has_display and not is_ssh and interactive_tty


def _load_html_template() -> str:
    return (
        files("ledgermind_local.installer")
        .joinpath("web_ui/index.html")
        .read_text(encoding="utf-8")
    )


def _sanitized_existing_config(config: InstallerConfig | None) -> dict[str, Any] | None:
    if config is None:
        return None
    payload = config.model_dump(mode="json", exclude_none=True)
    generation = payload.get("generation")
    if isinstance(generation, dict):
        generation.pop("token", None)
    embedding = payload.get("embedding")
    if isinstance(embedding, dict) and isinstance(embedding.get("api"), dict):
        embedding["api"].pop("token", None)
    reranker = payload.get("reranker")
    if isinstance(reranker, dict) and isinstance(reranker.get("api"), dict):
        reranker["api"].pop("token", None)
    decision = payload.get("resolution_decision")
    if isinstance(decision, dict):
        decision.pop("token", None)
    return payload


@dataclass
class _WebInstallState:
    status: str = "idle"  # idle | running | success | failed
    phase: str = "idle"
    message: str = ""
    events: list[dict[str, str]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    error_type: str | None = None
    cancelled: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    done_event: threading.Event = field(default_factory=threading.Event)

    def record_progress(self, phase: str, message: str) -> None:
        with self.lock:
            self.phase = phase
            self.message = message
            self.events.append({"phase": phase, "message": message})

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "status": self.status,
                "phase": self.phase,
                "message": self.message,
                "events": list(self.events),
                "result": self.result,
                "error": self.error,
                "error_type": self.error_type,
            }


def _collect_preflight_payload(
    *,
    preflight_home: Path | None,
    embedding_catalog: Sequence[dict[str, object]],
    existing_config: InstallerConfig | None,
) -> dict[str, Any]:
    from .paths import InstallerPaths

    paths = InstallerPaths(home_override=preflight_home)
    preflight = check_preflight(paths, require_bubblewrap=False)
    devices = [device.as_dict() for device in detect_devices()]
    agents: list[dict[str, Any]] = []
    for target_id in target_ids():
        adapter = get_target_adapter(target_id)
        discovery = adapter.discover()
        agents.append(
            {
                "id": target_id,
                "label": adapter.label,
                "detected": discovery.detected,
                "detail": discovery.detail,
                "location": str(discovery.config_dir or discovery.home or ""),
            }
        )
    defaults = load_model_defaults()
    local_entry = next(
        (
            dict(entry)
            for entry in embedding_catalog
            if entry.get("id") == defaults.embedding_local_catalog_id
        ),
        None,
    )
    reranker_revision = _RERANKER_FALLBACK_REVISION
    try:
        from ledgermind_local.inference.retrieval_reranker import MODEL_REVISION

        reranker_revision = MODEL_REVISION
    except ImportError:
        pass
    return {
        "preflight": preflight,
        "devices": devices,
        "agents": agents,
        "defaults": {
            **asdict(defaults),
            "openrouter_base_url": "https://openrouter.ai/api/v1",
            "nvidia_nim_base_url": "https://integrate.api.nvidia.com/v1",
        },
        "local_embedding_entry": local_entry,
        "reranker_model_revision": reranker_revision,
        "existing_config": _sanitized_existing_config(existing_config),
    }


def start_web_wizard_server(
    *,
    install_callback: Callable[
        [InstallerConfig, Callable[[str, str], None]], dict[str, Any]
    ],
    port: int = 0,
    preflight_home: Path | None = None,
    embedding_catalog: Sequence[dict[str, object]] = (),
    existing_config: InstallerConfig | None = None,
    openrouter_endpoint_loader: Callable[
        [str, str], tuple[OpenRouterEndpoint, ...]
    ] = lambda model, token: list_openrouter_model_endpoints(model, token=token),
    embedding_dimension_loader: Callable[[EmbeddingApiConfig, str], int] | None = None,
) -> tuple[ThreadingHTTPServer, str, _WebInstallState]:
    """Create and bind the 127.0.0.1 setup HTTP server."""

    session_token = secrets.token_urlsafe(32)
    html_template = _load_html_template()
    state = _WebInstallState()

    class SetupHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _send_security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")

        def _send_json(self, status: int, payload: object) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._send_security_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_text(self, status: int, text: str, content_type: str = "text/plain; charset=utf-8") -> None:
            encoded = text.encode("utf-8")
            self.send_response(status)
            self._send_security_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _valid_origin_and_host(self) -> bool:
            host = (self.headers.get("Host") or "").split(":", 1)[0].lower()
            if host and host not in {"127.0.0.1", "localhost", "[::1]"}:
                return False
            origin = self.headers.get("Origin")
            if origin:
                parsed = urlparse(origin)
                if (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
                    return False
            return True

        def _authorized_api(self) -> bool:
            if not self._valid_origin_and_host():
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "forbidden origin"})
                return False
            token = self.headers.get(_TOKEN_HEADER, "")
            if not token or not hmac.compare_digest(token, session_token):
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "invalid setup token"})
                return False
            return True

        def _read_json_body(self) -> dict[str, Any]:
            length_raw = self.headers.get("Content-Length", "0")
            try:
                length = int(length_raw)
            except ValueError as exc:
                raise ValueError("invalid Content-Length") from exc
            if length < 0 or length > _MAX_REQUEST_BYTES:
                raise ValueError("request body size out of bounds")
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                raise TypeError("request body must be a JSON object")
            return payload

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                if not self._valid_origin_and_host():
                    self._send_text(HTTPStatus.FORBIDDEN, "Forbidden host.")
                    return
                params = parse_qs(parsed.query)
                token = params.get("token", [""])[0]
                if not token or not hmac.compare_digest(token, session_token):
                    self._send_text(
                        HTTPStatus.FORBIDDEN,
                        "Invalid or missing setup session token. Open the exact URL printed in the terminal.",
                    )
                    return
                page = html_template.replace(
                    "__LEDGERMIND_SETUP_TOKEN__", json.dumps(session_token)
                )
                self._send_text(HTTPStatus.OK, page, "text/html; charset=utf-8")
                return
            if parsed.path == "/api/preflight":
                if not self._authorized_api():
                    return
                try:
                    data = _collect_preflight_payload(
                        preflight_home=preflight_home,
                        embedding_catalog=embedding_catalog,
                        existing_config=existing_config,
                    )
                    self._send_json(HTTPStatus.OK, data)
                except Exception as exc:  # noqa: BLE001
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            if parsed.path == "/api/status":
                if not self._authorized_api():
                    return
                self._send_json(HTTPStatus.OK, state.snapshot())
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if not self._authorized_api():
                return
            try:
                body = self._read_json_body()
            except Exception as exc:  # noqa: BLE001
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            if parsed.path == "/api/openrouter/endpoints":
                model = str(body.get("model") or "").strip()
                token = str(body.get("token") or "").strip()
                try:
                    endpoints = openrouter_endpoint_loader(model, token)
                    self._send_json(
                        HTTPStatus.OK,
                        {
                            "endpoints": [
                                {
                                    "route": item.route,
                                    "provider": item.provider,
                                    "label": item.label,
                                    "detail": item.detail,
                                    "quantization": item.quantization,
                                    "context_length": item.context_length,
                                    "prompt_price": item.prompt_price,
                                    "completion_price": item.completion_price,
                                }
                                for item in endpoints
                            ]
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            if parsed.path == "/api/embedding/dimensions":
                endpoint = str(body.get("endpoint") or "").strip()
                model = str(body.get("model") or "").strip()
                token = str(body.get("token") or "").strip()
                try:
                    provisional = EmbeddingApiConfig(
                        endpoint=endpoint,
                        token=token,
                        model=model,
                        dimensions=1536,
                    )
                    if embedding_dimension_loader is None:
                        dimensions = discover_embedding_dimensions(
                            provisional, token=token
                        )
                    else:
                        dimensions = embedding_dimension_loader(provisional, token)
                    self._send_json(HTTPStatus.OK, {"dimensions": dimensions})
                except Exception as exc:  # noqa: BLE001
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            if parsed.path == "/api/install":
                try:
                    config = InstallerConfig.model_validate(body)
                except Exception as exc:  # noqa: BLE001
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                with state.lock:
                    if state.status == "running":
                        self._send_json(
                            HTTPStatus.CONFLICT,
                            {"error": "installation is already running"},
                        )
                        return
                    if state.status == "success":
                        self._send_json(
                            HTTPStatus.CONFLICT,
                            {"error": "installation has already completed"},
                        )
                        return
                    state.status = "running"
                    state.phase = "starting"
                    state.message = "Starting installation"
                    state.events = [{"phase": "starting", "message": "Starting installation"}]
                    state.result = None
                    state.error = None
                    state.error_type = None

                def run_job() -> None:
                    try:
                        payload = install_callback(config, state.record_progress)
                    except Exception as exc:  # noqa: BLE001
                        with state.lock:
                            state.status = "failed"
                            state.error = str(exc)
                            state.error_type = type(exc).__name__
                            state.message = str(exc)
                            state.events.append({"phase": "failed", "message": str(exc)})
                    else:
                        with state.lock:
                            state.status = "success"
                            state.phase = "complete"
                            state.message = "Installation completed"
                            state.result = payload

                threading.Thread(
                    target=run_job, name="ledgermind-web-install", daemon=True
                ).start()
                self._send_json(HTTPStatus.ACCEPTED, {"status": "running"})
                return

            if parsed.path == "/api/shutdown":
                action = str(body.get("action") or "").strip().lower()
                with state.lock:
                    if state.status != "success" or action == "cancel":
                        state.cancelled = True
                state.done_event.set()
                self._send_json(HTTPStatus.OK, {"status": "closing"})
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    server = ThreadingHTTPServer(("127.0.0.1", port), SetupHandler)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/?token={session_token}"
    return server, url, state


def run_web_install(
    *,
    install_callback: Callable[
        [InstallerConfig, Callable[[str, str], None]], dict[str, Any]
    ],
    port: int = 0,
    open_browser: bool = True,
    output: TextIO = sys.stderr,
    preflight_home: Path | None = None,
    embedding_catalog: Sequence[dict[str, object]] = (),
    existing_config: InstallerConfig | None = None,
    openrouter_endpoint_loader: Callable[
        [str, str], tuple[OpenRouterEndpoint, ...]
    ] = lambda model, token: list_openrouter_model_endpoints(model, token=token),
    embedding_dimension_loader: Callable[[EmbeddingApiConfig, str], int] | None = None,
) -> dict[str, Any]:
    """Serve the localhost setup UI and block until installation completes or cancels."""

    server, url, state = start_web_wizard_server(
        install_callback=install_callback,
        port=port,
        preflight_home=preflight_home,
        embedding_catalog=embedding_catalog,
        existing_config=existing_config,
        openrouter_endpoint_loader=openrouter_endpoint_loader,
        embedding_dimension_loader=embedding_dimension_loader,
    )
    server_thread = threading.Thread(
        target=server.serve_forever, name="ledgermind-web-ui", daemon=True
    )
    server_thread.start()
    print("\nLedgerMind Web Setup", file=output)
    print(f"  Open in your browser: {url}", file=output)
    print("  (Run with --cli instead to use the terminal wizard.)", file=output)
    output.flush()
    if open_browser:
        try:
            webbrowser.open(url, new=1, autoraise=True)
        except Exception as exc:  # noqa: BLE001
            logger.debug("could not open browser automatically: %s", exc)

    try:
        while not state.done_event.wait(timeout=0.5):
            continue
    except KeyboardInterrupt as exc:
        with state.lock:
            if state.status == "success" and state.result is not None:
                return state.result
        raise UserCancelledError("installation cancelled by user") from exc
    finally:
        server.shutdown()
        server.server_close()

    with state.lock:
        if state.status == "success" and state.result is not None and not state.cancelled:
            return state.result
    raise UserCancelledError("installation cancelled by user")


__all__ = [
    "run_web_install",
    "should_use_web_ui",
    "start_web_wizard_server",
]
