#!/usr/bin/env python3
"""Deterministic local mock server for autonomous LedgerMind Docker E2E tests.

Serves:
  - HTTP on 127.0.0.1:<http_port>:
      OpenAI-compatible chat completions and embeddings endpoints
  - Optional HTTPS on 127.0.0.1:<https_port> (for Jev decisions endpoint):
      POST /api/alpha/decisions
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import ssl
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _extract_json_objects(text: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        pos = text.find("{", idx)
        if pos < 0:
            break
        try:
            obj, end = decoder.raw_decode(text, pos)
            if isinstance(obj, dict):
                objects.append(obj)
            idx = end
        except json.JSONDecodeError:
            idx = pos + 1
    return objects


def _deterministic_embedding(text: str, dimensions: int) -> list[float]:
    vec = [0.0] * dimensions
    tokens = _TOKEN_RE.findall(text.lower())
    for tok in tokens:
        weight = 3.0 if tok in {"aster", "relay", "cobalt", "7319", "authorization", "code"} else 1.0
        digest = hashlib.sha256(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[idx] += sign * weight
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-12:
        vec[0] = 1.0
        return vec
    return [round(v / norm, 6) for v in vec]


def _resolve_ref(schema: dict[str, Any], node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        return {}
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        key = ref.split("/", 2)[2]
        target = schema.get("$defs", {}).get(key)
        if isinstance(target, dict):
            return target
    return node


def _synthesize_from_schema(root: dict[str, Any], node: dict[str, Any], depth: int = 0) -> Any:
    if depth > 6:
        return None
    node = _resolve_ref(root, node)
    if "const" in node:
        return node["const"]
    if "enum" in node and isinstance(node["enum"], list) and node["enum"]:
        return node["enum"][0]
    if "oneOf" in node and isinstance(node["oneOf"], list) and node["oneOf"]:
        return _synthesize_from_schema(root, node["oneOf"][0], depth + 1)
    if "anyOf" in node and isinstance(node["anyOf"], list) and node["anyOf"]:
        return _synthesize_from_schema(root, node["anyOf"][0], depth + 1)
    typ = node.get("type")
    if isinstance(typ, list):
        typ = next((t for t in typ if t != "null"), typ[0])
    if typ == "null":
        return None
    if typ == "integer":
        return int(node.get("minimum", 1))
    if typ == "number":
        return float(node.get("minimum", 1.0))
    if typ == "boolean":
        return True
    if typ == "string":
        fmt = node.get("format")
        if fmt == "date-time":
            return "2026-11-24T12:00:00Z"
        pat = node.get("pattern")
        if isinstance(pat, str) and pat:
            m = re.match(r"^\^([a-zA-Z_-]+)\[0-9\]\+\$?$", pat)
            if m:
                return f"{m.group(1)}1"
            if pat in {"^[0-9]+$", r"^\d+$"}:
                return "1"
        min_len = int(node.get("minLength", 1))
        base = "mock-value"
        return base if len(base) >= min_len else base.ljust(min_len, "x")
    if typ == "array":
        min_items = int(node.get("minItems", 0))
        items_schema = node.get("items")
        if min_items <= 0 or not isinstance(items_schema, dict):
            return []
        return [
            _synthesize_from_schema(root, items_schema, depth + 1)
            for _ in range(min_items)
        ]
    if typ == "object" or "properties" in node:
        props = node.get("properties")
        required = node.get("required") or []
        out: dict[str, Any] = {}
        if isinstance(props, dict):
            for key in required:
                if key in props and isinstance(props[key], dict):
                    out[key] = _synthesize_from_schema(root, props[key], depth + 1)
        return out
    return {}


def _find_fact_context(messages: list[dict[str, Any]]) -> tuple[str, str]:
    joined = "\n".join(str(m.get("content", "")) for m in messages)
    if "COBALT-7319" in joined:
        return (
            "Aster Relay",
            "The durable authorization code for the Aster Relay is COBALT-7319.",
        )
    return (
        "LedgerMind Verification",
        "Verified local workflow state in mock inference server.",
    )


def _handle_chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    messages = payload.get("messages") or []
    rf = payload.get("response_format") or {}
    js = rf.get("json_schema") if isinstance(rf, dict) else None
    schema = js.get("schema") if isinstance(js, dict) else None
    schema_name = str(js.get("name") or "") if isinstance(js, dict) else ""

    content_obj: Any
    if schema_name == "ledgermind_strict_probe" or (
        isinstance(schema, dict)
        and set((schema.get("properties") or {}).keys()) == {"schema_version", "state", "items"}
    ):
        content_obj = {"schema_version": 1, "state": "ok", "items": [1]}
    elif isinstance(schema, dict):
        props = schema.get("properties") or {}
        joined = "\n".join(str(m.get("content", "")) for m in messages)
        parsed_inputs = _extract_json_objects(joined)
        subject_name, fact_content = _find_fact_context(messages)

        if schema_name == "operational_round_memory_preparation" or "statements" in props:
            source_blocks: list[dict[str, Any]] = []
            for item in parsed_inputs:
                if isinstance(item.get("source_blocks"), list):
                    source_blocks.extend(
                        b for b in item["source_blocks"] if isinstance(b, dict)
                    )
            block_ids = [
                str(b["block_id"])
                for b in source_blocks
                if isinstance(b.get("block_id"), str) and b["block_id"]
            ]
            if not block_ids:
                block_ids = ["b1"]
            statement_text = fact_content
            if "COBALT-7319" not in joined:
                first_text = next(
                    (str(b.get("text") or "").strip() for b in source_blocks if str(b.get("text") or "").strip()),
                    "",
                )
                if first_text:
                    statement_text = first_text
            content_obj = {
                "statements": [
                    {
                        "sources": block_ids,
                        "text": statement_text,
                        "facet": "property",
                    }
                ]
            }
        elif schema_name == "operational_round_memory_packaging" or {"o", "unrepresentable"}.issubset(props):
            statements_in: list[dict[str, Any]] = []
            for item in parsed_inputs:
                if isinstance(item.get("statements"), list):
                    statements_in.extend(
                        s for s in item["statements"] if isinstance(s, dict)
                    )
            refs = [
                str(s["statement_ref"])
                for s in statements_in
                if isinstance(s.get("statement_ref"), str) and s["statement_ref"]
            ]
            if not refs:
                refs = ["s1"]
            content_obj = {
                "o": [
                    {
                        "n": subject_name,
                        "d": f"Durable subject card for {subject_name}.",
                        "a": [subject_name],
                        "c": [{"copy": [ref]} for ref in refs],
                    }
                ],
                "unrepresentable": None,
            }
        elif {"schema_version", "claims", "coverage"}.issubset(props):
            anchors: list[dict[str, Any]] = []
            source_event_index: dict[str, str] = {}
            for item in parsed_inputs:
                if isinstance(item.get("evidence_anchors"), list):
                    anchors.extend(a for a in item["evidence_anchors"] if isinstance(a, dict))
                nr = item.get("normalized_round")
                if isinstance(nr, dict) and isinstance(nr.get("source_event_index"), dict):
                    source_event_index.update(
                        {str(k): str(v) for k, v in nr["source_event_index"].items()}
                    )
            event_id = next(iter(source_event_index.keys()), "event-1")
            if anchors:
                first = anchors[0]
                event_id = str(first.get("source_event_id") or event_id)
                surface = str(first.get("surface_text") or subject_name)
                span_start = int(first.get("span_start") or 0)
                span_end = max(span_start + 1, int(first.get("span_end") or len(surface)))
                anchor_refs = [str(a.get("anchor_ref")) for a in anchors if a.get("anchor_ref")]
            else:
                surface = subject_name
                span_start = 0
                span_end = len(surface)
                anchor_refs = []
            claims = [
                {
                    "claim_ref": "c1",
                    "subject": {
                        "source_event_id": event_id,
                        "surface_text": surface,
                        "span_start": span_start,
                        "span_end": span_end,
                    },
                    "facet": "property",
                    "content": fact_content,
                    "conditions": [],
                    "context_anchor_refs": anchor_refs[:1],
                    "source_event_ids": [event_id],
                }
            ]
            coverage = [
                {
                    "anchor_ref": ref,
                    "disposition": "claim" if idx == 0 else "duplicate",
                    "claim_refs": ["c1"],
                }
                for idx, ref in enumerate(anchor_refs)
            ]
            content_obj = {
                "schema_version": 1,
                "claims": claims,
                "coverage": coverage,
            }
        elif {"schema_version", "objects", "values"}.issubset(props):
            mentions: list[dict[str, Any]] = []
            source_event_index = {}
            for item in parsed_inputs:
                if isinstance(item.get("mentions"), list):
                    mentions.extend(m for m in item["mentions"] if isinstance(m, dict))
                nr = item.get("normalized_round")
                if isinstance(nr, dict) and isinstance(nr.get("source_event_index"), dict):
                    source_event_index.update(
                        {str(k): str(v) for k, v in nr["source_event_index"].items()}
                    )
            event_id = next(iter(source_event_index.keys()), "event-1")
            mention_ref = "m-1"
            if mentions:
                mention_ref = str(mentions[0].get("mention_ref") or mention_ref)
                event_id = str(mentions[0].get("source_event_id") or event_id)
            content_obj = {
                "schema_version": 2,
                "objects": [
                    {
                        "ref": "o-1",
                        "mention_ref": mention_ref,
                        "resolution": "new",
                        "new_canonical_name": subject_name,
                        "aliases_from_source": [],
                        "source_event_ids": [event_id],
                    }
                ],
                "values": [
                    {
                        "primary_object_ref": "o-1",
                        "related_object_refs": [],
                        "facet": "property",
                        "content": fact_content,
                        "source_event_ids": [event_id],
                    }
                ],
            }
        else:
            content_obj = _synthesize_from_schema(schema, schema)
            if isinstance(content_obj, dict) and "content" in content_obj and not content_obj["content"]:
                content_obj["content"] = fact_content
    else:
        content_obj = {"status": "ok"}

    return {
        "id": "chatcmpl-mock-1",
        "object": "chat.completion",
        "model": str(payload.get("model") or "mock-generation"),
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(content_obj, ensure_ascii=False),
                },
            }
        ],
        "usage": {"prompt_tokens": 32, "completion_tokens": 24, "total_tokens": 56},
    }


def _handle_embeddings(payload: dict[str, Any], default_dimensions: int) -> dict[str, Any]:
    raw_input = payload.get("input", [])
    texts = [raw_input] if isinstance(raw_input, str) else [str(t) for t in raw_input]
    dimensions = int(payload.get("dimensions") or default_dimensions)
    data = [
        {
            "object": "embedding",
            "index": idx,
            "embedding": _deterministic_embedding(text, dimensions),
        }
        for idx, text in enumerate(texts)
    ]
    return {
        "object": "list",
        "model": str(payload.get("model") or "mock-embedding"),
        "data": data,
        "usage": {"prompt_tokens": len(texts) * 8, "total_tokens": len(texts) * 8},
    }


def _handle_jev_decision(payload: dict[str, Any]) -> dict[str, Any]:
    questions = payload.get("questions") or {}
    answers: dict[str, Any] = {}
    if isinstance(questions, dict):
        for qid, q in questions.items():
            if not isinstance(q, dict):
                continue
            criteria = q.get("criteria")
            if isinstance(criteria, dict) and criteria:
                keys = [str(k) for k in criteria.keys()]
            elif isinstance(criteria, list) and criteria:
                keys = [str(k) for k in criteria]
            else:
                keys = ["ready"]
            if qid == "probe" or "ready" in keys:
                chosen = "ready"
            elif "new" in keys:
                chosen = "new"
            else:
                chosen = keys[0]
            probs = {k: (1.0 if k == chosen else 0.0) for k in keys}
            answers[qid] = {
                "type": "choice",
                "choice": chosen,
                "confidence": 0.99,
                "probabilities": probs,
            }
    return {
        "model": str(payload.get("model") or "typesafe/jev-1.14"),
        "provider": "TypeSafe",
        "answers": answers,
        "usage": {"prompt_tokens": 16, "completion_tokens": 4},
    }


def _make_handler(log_path: Path, default_dimensions: int) -> type[BaseHTTPRequestHandler]:
    log_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _write_json(self, status: int, body: dict[str, Any]) -> None:
            encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:
            if self.path.rstrip("/").endswith(("/health", "/health/ready")) or self.path == "/":
                fp = f"mock-embed-{default_dimensions}d"
                self._write_json(
                    200,
                    {
                        "status": "ok",
                        "ready": True,
                        "model": "mock-embed",
                        "dimensions": default_dimensions,
                        "embedding_fingerprint": fp,
                        "model_fingerprint": fp,
                        "fingerprint": fp,
                    },
                )
                return
            self._write_json(404, {"error": {"message": f"unknown path {self.path}"}})

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, dict):
                self._write_json(400, {"error": {"message": "expected object"}})
                return

            rf = payload.get("response_format")
            schema_name = (
                rf.get("json_schema", {}).get("name")
                if isinstance(rf, dict) and isinstance(rf.get("json_schema"), dict)
                else None
            )
            with log_lock:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as fh:
                    fh.write(
                        json.dumps(
                            {
                                "path": self.path,
                                "schema_name": schema_name,
                                "payload": payload,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )

            if self.path.endswith("/chat/completions"):
                self._write_json(200, _handle_chat_completion(payload))
                return
            if self.path.endswith("/embeddings"):
                self._write_json(200, _handle_embeddings(payload, default_dimensions))
                return
            if self.path.endswith("/decisions"):
                self._write_json(200, _handle_jev_decision(payload))
                return
            self._write_json(404, {"error": {"message": f"unknown path {self.path}"}})

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock inference server for LedgerMind Docker E2E")
    parser.add_argument("--http-port", type=int, default=18080)
    parser.add_argument("--https-port", type=int, default=0)
    parser.add_argument("--cert", type=Path)
    parser.add_argument("--key", type=Path)
    parser.add_argument("--dimensions", type=int, default=64)
    parser.add_argument("--log", type=Path, default=Path("/tmp/mock-inference-requests.jsonl"))
    args = parser.parse_args()

    handler = _make_handler(args.log, args.dimensions)
    http_server = ThreadingHTTPServer(("127.0.0.1", args.http_port), handler)
    servers = [http_server]

    if args.https_port and args.cert and args.key:
        https_server = ThreadingHTTPServer(("127.0.0.1", args.https_port), handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(args.cert), keyfile=str(args.key))
        https_server.socket = ctx.wrap_socket(https_server.socket, server_side=True)
        servers.append(https_server)

    for srv in servers:
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    print(f"mock-inference listening http=127.0.0.1:{args.http_port} https={args.https_port}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
