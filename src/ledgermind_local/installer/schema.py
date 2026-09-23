"""JSON schemas exposed to agents before they build an install config."""

from __future__ import annotations

from typing import Any

INSTALL_CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schema_version", "semantic_language", "generation", "embedding"],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": 2},
        "semantic_language": {
            "type": "string",
            "pattern": "^[A-Za-z]{2,8}(?:[-_][A-Za-z0-9]{1,8})*$",
            "examples": ["en", "pt", "uk", "zh-Hans"],
        },
        "memory_mode": {"enum": ["shared", "per_agent"]},
        "integrations": {
            "type": "array",
            "uniqueItems": True,
            "items": {"$ref": "#/$defs/integration"},
        },
        "memory_data_path": {"type": ["string", "null"]},
        "generation": {
            "type": "object",
            "required": ["endpoint", "model"],
            "additionalProperties": False,
            "properties": {
                "endpoint": {"type": "string", "format": "uri"},
                "provider_profile": {
                    "enum": ["openai_compatible", "openrouter", "nvidia_nim"]
                },
                "route": {"type": ["string", "null"]},
                "fallback_routes": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "maxItems": 1,
                    "uniqueItems": True,
                },
                "token": {"type": ["string", "null"]},
                "token_env": {"type": ["string", "null"]},
                "token_stdin": {"type": "boolean"},
                "secret_ref": {"type": ["string", "null"]},
                "model": {"type": "string"},
                "operational_model": {"type": ["string", "null"]},
                "object_resolution_model": {"type": ["string", "null"]},
                "background_model": {"type": ["string", "null"]},
                "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
                "max_concurrency": {"type": "integer", "minimum": 1},
                "structured_json_support": {"type": "boolean"},
            },
        },
        "embedding": {
            "type": "object",
            "required": ["mode"],
            "additionalProperties": False,
            "properties": {
                "mode": {"enum": ["api", "local"]},
                "api": {"$ref": "#/$defs/embeddingApi"},
                "local": {"$ref": "#/$defs/embeddingLocal"},
            },
            "oneOf": [
                {
                    "properties": {"mode": {"const": "api"}},
                    "required": ["api"],
                    "not": {"required": ["local"]},
                },
                {
                    "properties": {"mode": {"const": "local"}},
                    "required": ["local"],
                    "not": {"required": ["api"]},
                },
            ],
        },
        "reranker": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "mode": {"enum": ["disabled", "api", "local"]},
                "api": {"$ref": "#/$defs/rerankerApi"},
                "local": {"$ref": "#/$defs/rerankerLocal"},
            },
            "oneOf": [
                {"properties": {"mode": {"const": "disabled"}}},
                {"properties": {"mode": {"const": "api"}}, "required": ["api"]},
                {"properties": {"mode": {"const": "local"}}, "required": ["local"]},
            ],
        },
        "runtime": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "residency_mode": {
                    "type": "string",
                    "enum": ["session", "idle", "always_on"],
                },
                "idle_timeout_seconds": {"type": "number", "minimum": 0},
                "session_safety_ttl_seconds": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                },
                "idle_shutdown_seconds": {"type": "number", "minimum": 0},
                "lease_ttl_seconds": {"type": "number", "exclusiveMinimum": 0},
                "heartbeat_seconds": {"type": "number", "exclusiveMinimum": 0},
            },
        },
        "advanced": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "generation_max_input": {"type": ["integer", "null"], "minimum": 1},
                "generation_max_output": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                },
                "embedding_max_text_length": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                },
                "retry_attempts": {"type": "integer", "minimum": 0, "maximum": 10},
                "allow_custom_model": {"type": "boolean"},
                "custom_model_sha256": {"type": ["string", "null"]},
                "custom_runtime_compatibility": {"type": ["string", "null"]},
            },
        },
    },
    "$defs": {
        "rerankerApi": {
            "type": "object",
            "required": ["endpoint", "model"],
            "additionalProperties": False,
            "properties": {
                "endpoint": {"type": "string", "format": "uri"},
                "token": {"type": ["string", "null"]},
                "token_env": {"type": ["string", "null"]},
                "secret_ref": {"type": ["string", "null"]},
                "model": {"type": "string"},
                "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
            },
        },
        "rerankerLocal": {
            "type": "object",
            "required": ["model_path", "runtime_path"],
            "additionalProperties": False,
            "properties": {
                "model_path": {"type": "string"},
                "runtime_path": {"type": "string"},
                "device": {"enum": ["cpu", "cuda", "rocm"]},
            },
        },
        "integration": {
            "type": "object",
            "required": ["id"],
            "additionalProperties": False,
            "properties": {
                "id": {
                    "enum": [
                        "hermes",
                        "codex",
                        "claude-code",
                        "cursor",
                        "opencode",
                        "openclaw",
                    ]
                },
                "enabled": {"type": "boolean"},
            },
        },
        "embeddingApi": {
            "type": "object",
            "required": ["endpoint", "model", "dimensions"],
            "additionalProperties": False,
            "properties": {
                "endpoint": {"type": "string", "format": "uri"},
                "token": {"type": ["string", "null"]},
                "token_env": {"type": ["string", "null"]},
                "token_stdin": {"type": "boolean"},
                "secret_ref": {"type": ["string", "null"]},
                "model": {"type": "string"},
                "dimensions": {"type": "integer", "minimum": 1},
                "batch_size": {"type": "integer", "minimum": 1},
                "concurrency": {"type": "integer", "minimum": 1},
                "timeout_seconds": {"type": "number", "exclusiveMinimum": 0},
            },
        },
        "embeddingLocal": {
            "type": "object",
            "required": ["catalog_id"],
            "additionalProperties": False,
            "properties": {
                "catalog_id": {"type": "string"},
                "device": {"enum": ["auto", "cpu", "cuda", "rocm"]},
                "model_path": {"type": ["string", "null"]},
                "model_storage_path": {"type": ["string", "null"]},
                "runtime_id": {"type": ["string", "null"]},
                "runtime_path": {"type": ["string", "null"]},
                "dimensions": {"type": "integer", "minimum": 1},
                "batch_size": {"type": "integer", "minimum": 1},
                "concurrency": {"type": "integer", "minimum": 1},
                "threads": {"type": "integer", "minimum": 0},
                "gpu_allocation": {"type": "string"},
                "auto_start": {"type": "boolean"},
            },
        },
    },
}


INSTALL_MANIFEST_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version",
        "release_version",
        "published_at",
        "public_key_fingerprint",
        "platforms",
        "components",
        "embedding_catalog",
    ],
    "properties": {
        "schema_version": {"type": "integer", "minimum": 1},
        "release_version": {"type": "string"},
        "published_at": {"type": "string"},
        "public_key_fingerprint": {"type": "string"},
        "platforms": {
            "type": "object",
            "additionalProperties": {"$ref": "#/$defs/platform"},
        },
        "components": {"type": "object", "additionalProperties": {"type": "object"}},
        "embedding_catalog": {"type": "array"},
    },
    "$defs": {
        "artifact": {
            "type": "object",
            "required": ["url", "size", "sha256", "platform"],
            "additionalProperties": False,
            "properties": {
                "url": {"type": "string", "minLength": 1},
                "size": {"type": "integer", "minimum": 0},
                "sha256": {"type": "string", "pattern": "^[0-9a-fA-F]{64}$"},
                "signature": {"type": ["string", "null"]},
                "platform": {"type": "string", "minLength": 1},
                "minimum_glibc": {"type": ["string", "null"]},
                "component_compatibility": {"type": "object"},
            },
        },
        "platform": {
            "type": "object",
            "required": ["installer", "bundle"],
            "additionalProperties": False,
            "properties": {
                "installer": {"$ref": "#/$defs/artifact"},
                "bundle": {"$ref": "#/$defs/artifact"},
            },
        },
    },
}


INSTALL_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "status",
        "operation",
        "exit_code",
        "steps",
        "warnings",
        "errors",
        "paths",
        "profiles",
        "runtime",
        "smoke_test",
    ],
    "properties": {
        "status": {"type": "string"},
        "operation": {"type": "string"},
        "exit_code": {"type": "integer"},
        "steps": {"type": "array"},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "errors": {"type": "array", "items": {"type": "string"}},
        "paths": {"type": "object"},
        "profiles": {"type": "array"},
        "runtime": {"type": "object"},
        "smoke_test": {"type": "object"},
    },
}


def schema(name: str) -> dict[str, Any]:
    schemas = {
        "install-config": INSTALL_CONFIG_SCHEMA,
        "install-manifest": INSTALL_MANIFEST_SCHEMA,
        "install-result": INSTALL_RESULT_SCHEMA,
    }
    try:
        return schemas[name]
    except KeyError as exc:
        raise KeyError(f"unknown installer schema: {name}") from exc


def validate_config_payload(payload: object) -> object:
    from .models import InstallerConfig

    return InstallerConfig.model_validate(payload)


__all__ = [
    "INSTALL_CONFIG_SCHEMA",
    "INSTALL_MANIFEST_SCHEMA",
    "INSTALL_RESULT_SCHEMA",
    "schema",
    "validate_config_payload",
]
