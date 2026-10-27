#!/usr/bin/env python3
"""Minimal OpenRouter proxy used only by the isolated integration E2E.

It pins every inference request to the benchmark model and provider route.
Credentials remain in the process environment and are never written to logs.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


MODEL = os.environ.get("LEDGERMIND_E2E_MODEL", "deepseek/deepseek-v4-flash-0731")
ROUTE = os.environ.get("LEDGERMIND_E2E_ROUTE", "baidu/fp8")
TOKEN = os.environ["OPENROUTER_API_KEY"]
LOG_PATH = Path(os.environ.get("LEDGERMIND_E2E_PROXY_LOG", "/reports/provider-calls.jsonl"))
UPSTREAM = "https://openrouter.ai/api"


def _log(payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise TypeError("request body is not an object")
        except (json.JSONDecodeError, TypeError) as exc:
            self.send_error(400, str(exc))
            return

        requested_model = body.get("model")
        body["model"] = MODEL
        body["provider"] = {
            "order": [ROUTE],
            "allow_fallbacks": False,
            "require_parameters": False,
        }
        body["reasoning_effort"] = "none"
        payload = json.dumps(body, ensure_ascii=False).encode()
        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Accept": self.headers.get("accept", "application/json"),
            "Accept-Encoding": "identity",
            "X-OpenRouter-Metadata": "enabled",
        }
        request = urllib.request.Request(
            f"{UPSTREAM}{self.path}", data=payload, headers=headers, method="POST"
        )
        _log(
            {
                "event": "request_started",
                "path": self.path,
                "requested_model": requested_model,
                "enforced_model": MODEL,
                "enforced_route": ROUTE,
                "fallbacks": False,
            }
        )
        status = 502
        response_headers: Any = {}
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                status = response.status
                response_body = response.read()
                response_headers = response.headers
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_body = exc.read()
            response_headers = exc.headers
        except Exception as exc:  # pragma: no cover - real network boundary
            response_body = json.dumps(
                {"error": {"message": f"proxy upstream error: {type(exc).__name__}"}}
            ).encode()

        provider = None
        response_model = None
        usage = None
        try:
            decoded = json.loads(response_body)
            if isinstance(decoded, dict):
                provider = decoded.get("provider")
                response_model = decoded.get("model")
                usage = decoded.get("usage")
        except json.JSONDecodeError:
            pass
        _log(
            {
                "path": self.path,
                "status": status,
                "requested_model": requested_model,
                "enforced_model": MODEL,
                "enforced_route": ROUTE,
                "fallbacks": False,
                "response_model": response_model,
                "response_provider": provider,
                "usage": usage,
            }
        )

        self.send_response(status)
        content_type = response_headers.get("content-type", "application/json")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)


def main() -> None:
    host = os.environ.get("LEDGERMIND_E2E_PROXY_HOST", "127.0.0.1")
    port = int(os.environ.get("LEDGERMIND_E2E_PROXY_PORT", "18790"))
    _log({"event": "proxy_started", "model": MODEL, "route": ROUTE})
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
