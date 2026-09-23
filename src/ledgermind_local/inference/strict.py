"""Core-owned strict structured-output validation at the Local boundary.

Local may select a provider adapter, but it must not downgrade a Core
semantic request to another response mode. This module validates the opaque
strict requirement and keeps the provider-facing schema profile portable.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence

STRICT_JSON_SCHEMA_MODE = "strict_json_schema"
# Core and Lab own the portable strict-schema profile identifier.  Keep the
# Local boundary byte-for-byte aligned with that wire contract; a version
# suffix here makes every Core-issued semantic task fail before HTTP.
STRICT_SCHEMA_PROFILE_VERSION = "ledgermind-strict-schema"

_PROFILE_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "enum",
        "description",
        "minLength",
        "maxLength",
        "pattern",
        "$defs",
        "$ref",
        "oneOf",
    }
)


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _types(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def validate_strict_schema_profile(schema: object) -> dict[str, object]:
    if not isinstance(schema, Mapping):
        raise ValueError("strict schema must be an object")

    definitions = schema.get("$defs", {})
    if not isinstance(definitions, Mapping):
        raise ValueError("strict schema $defs must be an object")

    def visit(node: object, path: str, *, root: bool = False) -> None:
        if not isinstance(node, Mapping):
            raise ValueError(f"strict schema node {path} must be an object")
        unsupported = sorted(set(node) - _PROFILE_KEYWORDS)
        if unsupported:
            raise ValueError(
                f"strict schema node {path} uses unsupported keywords: {', '.join(unsupported)}"
            )
        if "$defs" in node and not root:
            raise ValueError(f"strict schema node {path} may not declare $defs")
        reference = node.get("$ref")
        if reference is not None:
            if not isinstance(reference, str) or not reference.startswith("#/$defs/"):
                raise ValueError(f"strict schema reference at {path} must be local")
            definition_name = reference.removeprefix("#/$defs/")
            if (
                not definition_name
                or "/" in definition_name
                or definition_name not in definitions
            ):
                raise ValueError(f"strict schema reference at {path} is unknown")
            if set(node) != {"$ref"}:
                raise ValueError(
                    f"strict schema reference at {path} must not have siblings"
                )
            return
        alternatives = node.get("oneOf")
        if alternatives is not None:
            if (
                not isinstance(alternatives, Sequence)
                or isinstance(alternatives, (str, bytes, bytearray))
                or not alternatives
            ):
                raise ValueError(
                    f"strict schema oneOf at {path} must be a non-empty array"
                )
            for index, alternative in enumerate(alternatives):
                visit(alternative, f"{path}.oneOf[{index}]")
        types = _types(node.get("type"))
        if not types and "enum" not in node and alternatives is None:
            raise ValueError(f"strict schema node {path} must declare a type")
        known = {"object", "array", "string", "integer", "number", "boolean", "null"}
        if any(item not in known for item in types):
            raise ValueError(f"strict schema node {path} has an unsupported type")
        if "object" in types:
            if node.get("additionalProperties") is not False:
                raise ValueError(f"strict schema object {path} must set additionalProperties=false")
            properties = node.get("properties", {})
            if not isinstance(properties, Mapping):
                raise ValueError(f"strict schema properties at {path} must be an object")
            for name, child in properties.items():
                if not isinstance(name, str) or not name.strip():
                    raise ValueError(f"strict schema property name at {path} is invalid")
                visit(child, f"{path}.properties.{name}")
            required = node.get("required", [])
            if not isinstance(required, Sequence) or isinstance(required, (str, bytes, bytearray)):
                raise ValueError(f"strict schema required at {path} must be an array")
            if any(not isinstance(name, str) or name not in properties for name in required):
                raise ValueError(f"strict schema required at {path} references an unknown property")
        if "array" in types or "items" in node:
            if "items" not in node:
                raise ValueError(f"strict schema array {path} must declare items")
            visit(node["items"], f"{path}.items")
            for keyword in ("minItems", "maxItems"):
                value = node.get(keyword)
                if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                    raise ValueError(f"strict schema {keyword} at {path} must be a non-negative integer")
            if isinstance(node.get("minItems"), int) and isinstance(node.get("maxItems"), int):
                if node["minItems"] > node["maxItems"]:
                    raise ValueError(f"strict schema minItems exceeds maxItems at {path}")
        if "enum" in node:
            values = node["enum"]
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)) or not values:
                raise ValueError(f"strict schema enum at {path} must be a non-empty array")
        if "pattern" in node:
            pattern = node["pattern"]
            if "string" not in types or not isinstance(pattern, str) or not pattern:
                raise ValueError(
                    f"strict schema pattern at {path} requires a non-empty string type"
                )
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"strict schema pattern at {path} is invalid") from exc
        for keyword in ("minLength", "maxLength"):
            value = node.get(keyword)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"strict schema {keyword} at {path} must be a non-negative integer")
        if isinstance(node.get("minLength"), int) and isinstance(node.get("maxLength"), int):
            if node["minLength"] > node["maxLength"]:
                raise ValueError(f"strict schema minLength exceeds maxLength at {path}")
        if root and "object" not in types:
            raise ValueError("strict semantic schema root must be an object")

        if root:
            for name, definition in definitions.items():
                if not isinstance(name, str) or not name or "/" in name:
                    raise ValueError("strict schema definition name is invalid")
                visit(definition, f"$.$defs.{name}")

    visit(schema, "$", root=True)
    return dict(schema)


def strict_requirement_for_contract(contract: Mapping[str, object]) -> dict[str, object]:
    schema = contract.get("json_schema")
    if not isinstance(schema, Mapping):
        raise ValueError("strict request requires output_contract.json_schema")
    normalized = validate_strict_schema_profile(schema)
    digest = canonical_digest(normalized)
    contract_digest = contract.get("schema_digest")
    if isinstance(contract_digest, str) and contract_digest and contract_digest != digest:
        raise ValueError("output contract schema_digest does not match json_schema")
    return {
        "mode": STRICT_JSON_SCHEMA_MODE,
        "schema_version": contract.get("schema_version", 1),
        "schema": normalized,
        "schema_digest": digest,
        "schema_profile_version": STRICT_SCHEMA_PROFILE_VERSION,
        "strict": True,
    }


def validate_strict_requirement(
    requirement: Mapping[str, object] | None,
    contract: Mapping[str, object] | None,
) -> dict[str, object]:
    if not isinstance(requirement, Mapping):
        if not isinstance(contract, Mapping):
            raise ValueError("strict request requires structured_output_requirement")
        return strict_requirement_for_contract(contract)
    if requirement.get("mode") != STRICT_JSON_SCHEMA_MODE:
        raise ValueError("structured output requirement must use strict_json_schema")
    if requirement.get("schema_profile_version") != STRICT_SCHEMA_PROFILE_VERSION:
        raise ValueError("unsupported LedgerMind strict schema profile")
    if requirement.get("strict") is not True:
        raise ValueError("strict structured output requirement must set strict=true")
    schema = validate_strict_schema_profile(requirement.get("schema"))
    digest = canonical_digest(schema)
    if requirement.get("schema_digest") != digest:
        raise ValueError("strict structured output schema digest mismatch")
    if isinstance(contract, Mapping):
        contract_requirement = strict_requirement_for_contract(contract)
        if contract_requirement["schema_digest"] != digest:
            raise ValueError("strict requirement schema differs from Core output contract")
    return {
        "mode": STRICT_JSON_SCHEMA_MODE,
        "schema_version": requirement.get("schema_version"),
        "schema": schema,
        "schema_digest": digest,
        "schema_profile_version": STRICT_SCHEMA_PROFILE_VERSION,
        "strict": True,
    }


__all__ = [
    "STRICT_JSON_SCHEMA_MODE",
    "STRICT_SCHEMA_PROFILE_VERSION",
    "canonical_digest",
    "strict_requirement_for_contract",
    "validate_strict_requirement",
    "validate_strict_schema_profile",
]
