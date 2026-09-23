"""SQLite storage for Local inference profiles and egress metadata."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
import json
from typing import cast

from .profiles import (
    InferenceProfile,
    ProbeStatus,
    ProviderCapabilities,
    StructuredOutputMode,
    generation_profile_fingerprint,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _extra_body_from_row(row: sqlite3.Row) -> dict[str, object]:
    if "extra_body_json" not in row.keys():
        return {}
    raw = row["extra_body_json"]
    if not isinstance(raw, str):
        return {}
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


class InferenceProfileStore:
    """Repository over the profile tables in Local's rounds database."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

    @staticmethod
    def _profile_from_row(row: sqlite3.Row) -> InferenceProfile:
        return InferenceProfile.model_validate(
            {
                "profile_id": row["profile_id"],
                "provider_kind": row["provider_kind"],
                "base_url": row["base_url"],
                "model": row["model"],
                "secret_ref": row["secret_ref"],
                "timeout_seconds": row["timeout_seconds"],
                "max_retries": row["max_retries"],
                "max_input_tokens": row["max_input_tokens"],
                "max_output_tokens": row["max_output_tokens"],
                "extra_body": _extra_body_from_row(row),
                "structured_output_preference": row["structured_output_preference"],
                "token_parameter": row["token_parameter"],
                "supports_system_role": bool(row["supports_system_role"]),
                "supports_seed": bool(row["supports_seed"]),
                "enabled": bool(row["enabled"]),
            }
        )

    @staticmethod
    def _capabilities_from_row(row: sqlite3.Row) -> ProviderCapabilities:
        columns = set(row.keys())
        detected: dict[str, object] = {}
        raw_detected = row["detected_capabilities_json"] if "detected_capabilities_json" in columns else "{}"
        if isinstance(raw_detected, str):
            try:
                decoded = json.loads(raw_detected)
            except (TypeError, ValueError):
                decoded = {}
            if isinstance(decoded, dict):
                detected = decoded
        return ProviderCapabilities(
            profile_id=row["profile_id"],
            profile_fingerprint=(row["profile_fingerprint"] if "profile_fingerprint" in columns else ""),
            transport=(row["transport"] if "transport" in columns else "openai_compatible"),
            model=(row["model"] if "model" in columns else ""),
            structured_output_mode=row["structured_output_mode"],
            json_schema_supported=bool(row["json_schema_supported"]),
            tool_call_supported=bool(row["tool_call_supported"]),
            json_object_supported=bool(row["json_object_supported"]),
            prompt_only_supported=bool(row["prompt_only_supported"]),
            structured_json_schema=bool(row["structured_json_schema"]) if "structured_json_schema" in columns else False,
            structured_json_object=bool(row["structured_json_object"]) if "structured_json_object" in columns else False,
            tool_calling=bool(row["tool_calling"]) if "tool_calling" in columns else False,
            plain_json_prompt=bool(row["plain_json_prompt"]) if "plain_json_prompt" in columns else False,
            native_schema_strictness=bool(row["native_schema_strictness"]) if "native_schema_strictness" in columns else False,
            max_input_tokens_known=row["max_input_tokens_known"] if "max_input_tokens_known" in columns else None,
            max_output_tokens_known=row["max_output_tokens_known"] if "max_output_tokens_known" in columns else None,
            supports_batch_embeddings=bool(row["supports_batch_embeddings"]) if "supports_batch_embeddings" in columns else False,
            embedding_max_batch=row["embedding_max_batch"] if "embedding_max_batch" in columns else None,
            detected_capabilities=detected,
            probe_contract_digest=row["probe_contract_digest"],
            probe_status=row["probe_status"],
            last_probed_at=row["last_probed_at"],
            last_error_code=row["last_error_code"],
            probed_at=(row["probed_at"] if "probed_at" in columns else None),
            expires_at=(row["expires_at"] if "expires_at" in columns else None),
            probe_result=(row["probe_result"] if "probe_result" in columns else row["probe_status"]),
            last_error=(row["last_error"] if "last_error" in columns else row["last_error_code"]),
        )

    def get(self, profile_id: str) -> InferenceProfile | None:
        row = self._connection.execute(
            "SELECT * FROM inference_profiles WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        return self._profile_from_row(row) if row is not None else None

    def list(self, *, enabled_only: bool = False) -> tuple[InferenceProfile, ...]:
        query = "SELECT * FROM inference_profiles"
        params: tuple[object, ...] = ()
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY profile_id"
        rows = self._connection.execute(query, params).fetchall()
        return tuple(self._profile_from_row(row) for row in rows)

    def list_ids(self, *, enabled_only: bool = False) -> tuple[str, ...]:
        return tuple(
            profile.profile_id for profile in self.list(enabled_only=enabled_only)
        )

    def upsert(self, profile: InferenceProfile) -> InferenceProfile:
        now = _now()
        previous = self.get(profile.profile_id)
        previous_capabilities = self.get_capabilities(profile.profile_id)
        values = profile.model_dump()
        extra_body_json = json.dumps(
            values["extra_body"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        self._connection.execute(
            """
            INSERT INTO inference_profiles (
                profile_id, provider_kind, base_url, model, secret_ref,
                timeout_seconds, max_retries, max_input_tokens, max_output_tokens,
                extra_body_json, structured_output_preference, token_parameter,
                supports_system_role, supports_seed, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                provider_kind = excluded.provider_kind,
                base_url = excluded.base_url,
                model = excluded.model,
                secret_ref = excluded.secret_ref,
                timeout_seconds = excluded.timeout_seconds,
                max_retries = excluded.max_retries,
                max_input_tokens = excluded.max_input_tokens,
                max_output_tokens = excluded.max_output_tokens,
                extra_body_json = excluded.extra_body_json,
                structured_output_preference = excluded.structured_output_preference,
                token_parameter = excluded.token_parameter,
                supports_system_role = excluded.supports_system_role,
                supports_seed = excluded.supports_seed,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                values["profile_id"],
                values["provider_kind"],
                values["base_url"],
                values["model"],
                values["secret_ref"],
                values["timeout_seconds"],
                values["max_retries"],
                values["max_input_tokens"],
                values["max_output_tokens"],
                extra_body_json,
                values["structured_output_preference"],
                values["token_parameter"],
                int(values["supports_system_role"]),
                int(values["supports_seed"]),
                int(values["enabled"]),
                now,
                now,
            ),
        )
        result = self.get(profile.profile_id)
        if result is None:
            raise RuntimeError("inference profile upsert did not produce a row")
        if previous is not None and previous != result and previous_capabilities is not None:
            old_fingerprint = previous_capabilities.profile_fingerprint
            new_fingerprint = generation_profile_fingerprint(result)
            if old_fingerprint and old_fingerprint != new_fingerprint:
                self.invalidate_capabilities(
                    result.profile_id,
                    reason="profile_fingerprint_changed",
                )
        return result

    def get_capabilities(
        self,
        profile_id: str,
        *,
        profile_fingerprint: str | None = None,
        fresh_only: bool = False,
        now: str | None = None,
    ) -> ProviderCapabilities | None:
        row = self._connection.execute(
            "SELECT * FROM inference_provider_capabilities WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
        if row is None:
            return None
        capabilities = self._capabilities_from_row(row)
        if profile_fingerprint is not None and capabilities.profile_fingerprint not in {
            "",
            profile_fingerprint,
        }:
            return None
        if fresh_only and profile_fingerprint is not None and not capabilities.is_fresh(
            profile_fingerprint=profile_fingerprint,
            now=now,
        ):
            return None
        return capabilities

    def get_capabilities_for_profile(
        self,
        profile: InferenceProfile,
        *,
        fresh_only: bool = False,
        now: str | None = None,
    ) -> ProviderCapabilities | None:
        return self.get_capabilities(
            profile.profile_id,
            profile_fingerprint=generation_profile_fingerprint(profile),
            fresh_only=fresh_only,
            now=now,
        )

    def list_capabilities(self) -> tuple[ProviderCapabilities, ...]:
        rows = self._connection.execute(
            "SELECT * FROM inference_provider_capabilities ORDER BY profile_id"
        ).fetchall()
        return tuple(self._capabilities_from_row(row) for row in rows)

    def upsert_capabilities(
        self,
        capabilities: ProviderCapabilities | None = None,
        *,
        profile_id: str | None = None,
        structured_output_mode: str = "auto",
        json_schema_supported: bool = False,
        tool_call_supported: bool = False,
        json_object_supported: bool = False,
        prompt_only_supported: bool = False,
        probe_contract_digest: str | None = None,
        probe_status: str = "unknown",
        last_probed_at: str | None = None,
        last_error_code: str | None = None,
        profile_fingerprint: str = "",
        transport: str = "openai_compatible",
        model: str = "",
        detected_capabilities: dict[str, object] | None = None,
        probed_at: str | None = None,
        expires_at: str | None = None,
        probe_result: str | None = None,
        last_error: str | None = None,
        structured_json_schema: bool = False,
        structured_json_object: bool = False,
        tool_calling: bool = False,
        plain_json_prompt: bool = False,
        native_schema_strictness: bool = False,
        max_input_tokens_known: int | None = None,
        max_output_tokens_known: int | None = None,
        supports_batch_embeddings: bool = False,
        embedding_max_batch: int | None = None,
    ) -> ProviderCapabilities:
        """Persist a content-free capability observation for a profile."""

        if capabilities is None:
            if profile_id is None:
                raise ValueError("profile_id is required for capability persistence")
            capabilities = ProviderCapabilities(
                profile_id=profile_id,
                profile_fingerprint=profile_fingerprint,
                transport=transport,
                model=model,
                structured_output_mode=cast(StructuredOutputMode, structured_output_mode),
                json_schema_supported=json_schema_supported,
                tool_call_supported=tool_call_supported,
                json_object_supported=json_object_supported,
                prompt_only_supported=prompt_only_supported,
                structured_json_schema=structured_json_schema,
                structured_json_object=structured_json_object,
                tool_calling=tool_calling,
                plain_json_prompt=plain_json_prompt,
                native_schema_strictness=native_schema_strictness,
                max_input_tokens_known=max_input_tokens_known,
                max_output_tokens_known=max_output_tokens_known,
                supports_batch_embeddings=supports_batch_embeddings,
                embedding_max_batch=embedding_max_batch,
                detected_capabilities=detected_capabilities or {},
                probe_contract_digest=probe_contract_digest,
                probe_status=cast(ProbeStatus, probe_status),
                last_probed_at=last_probed_at,
                last_error_code=last_error_code,
                probed_at=probed_at,
                expires_at=expires_at,
                probe_result=cast(ProbeStatus, probe_result or probe_status),
                last_error=last_error or last_error_code,
            )
        elif profile_id is not None and profile_id != capabilities.profile_id:
            raise ValueError("profile_id does not match capabilities")

        values = capabilities.model_dump(mode="python")
        detected_json = json.dumps(
            values.get("detected_capabilities", {}),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self._connection.execute(
            """
            INSERT INTO inference_provider_capabilities (
                profile_id, structured_output_mode, json_schema_supported,
                tool_call_supported, json_object_supported, prompt_only_supported,
                probe_contract_digest, probe_status, last_probed_at, last_error_code,
                profile_fingerprint, transport, model, detected_capabilities_json,
                probed_at, expires_at, probe_result, last_error,
                structured_json_schema, structured_json_object, tool_calling,
                plain_json_prompt, native_schema_strictness, max_input_tokens_known,
                max_output_tokens_known, supports_batch_embeddings, embedding_max_batch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id) DO UPDATE SET
                structured_output_mode = excluded.structured_output_mode,
                json_schema_supported = excluded.json_schema_supported,
                tool_call_supported = excluded.tool_call_supported,
                json_object_supported = excluded.json_object_supported,
                prompt_only_supported = excluded.prompt_only_supported,
                probe_contract_digest = excluded.probe_contract_digest,
                probe_status = excluded.probe_status,
                last_probed_at = excluded.last_probed_at,
                last_error_code = excluded.last_error_code,
                profile_fingerprint = excluded.profile_fingerprint,
                transport = excluded.transport,
                model = excluded.model,
                detected_capabilities_json = excluded.detected_capabilities_json,
                probed_at = excluded.probed_at,
                expires_at = excluded.expires_at,
                probe_result = excluded.probe_result,
                last_error = excluded.last_error,
                structured_json_schema = excluded.structured_json_schema,
                structured_json_object = excluded.structured_json_object,
                tool_calling = excluded.tool_calling,
                plain_json_prompt = excluded.plain_json_prompt,
                native_schema_strictness = excluded.native_schema_strictness,
                max_input_tokens_known = excluded.max_input_tokens_known,
                max_output_tokens_known = excluded.max_output_tokens_known,
                supports_batch_embeddings = excluded.supports_batch_embeddings,
                embedding_max_batch = excluded.embedding_max_batch
            """,
            (
                values["profile_id"],
                values["structured_output_mode"],
                int(values["json_schema_supported"]),
                int(values["tool_call_supported"]),
                int(values["json_object_supported"]),
                int(values["prompt_only_supported"]),
                values["probe_contract_digest"],
                values["probe_status"],
                values["last_probed_at"],
                values["last_error_code"],
                values["profile_fingerprint"],
                values["transport"],
                values["model"],
                detected_json,
                values["probed_at"],
                values["expires_at"],
                values["probe_result"],
                values["last_error"],
                int(values["structured_json_schema"]),
                int(values["structured_json_object"]),
                int(values["tool_calling"]),
                int(values["plain_json_prompt"]),
                int(values["native_schema_strictness"]),
                values["max_input_tokens_known"],
                values["max_output_tokens_known"],
                int(values["supports_batch_embeddings"]),
                values["embedding_max_batch"],
            ),
        )
        result = self.get_capabilities(capabilities.profile_id)
        if result is None:
            raise RuntimeError("provider capability upsert did not produce a row")
        return result

    save_capabilities = upsert_capabilities
    get_provider_capabilities = get_capabilities
    save_provider_capabilities = upsert_capabilities

    def invalidate_capabilities(self, profile_id: str, *, reason: str) -> bool:
        """Make a capability observation unusable without deleting evidence."""

        cursor = self._connection.execute(
            """
            UPDATE inference_provider_capabilities
               SET probe_status = 'unknown', probe_result = 'unknown',
                   expires_at = ?, last_error_code = ?, last_error = ?
             WHERE profile_id = ?
            """,
            (_now(), reason, reason, profile_id),
        )
        return cursor.rowcount == 1

    def record_capability_fallback(
        self,
        profile_id: str,
        *,
        failed_mode: StructuredOutputMode,
        successful_mode: StructuredOutputMode,
        error_code: str,
    ) -> bool:
        """Persist a successful bounded mode downgrade as fresh evidence."""

        capabilities = self.get_capabilities(profile_id)
        if capabilities is None:
            return False
        updated = capabilities.after_successful_fallback(
            failed_mode=failed_mode,
            successful_mode=successful_mode,
            error_code=error_code,
        )
        self.upsert_capabilities(updated)
        return True

    def record_probe_error(self, profile_id: str, *, error_code: str) -> bool:
        """Record an outage while retaining a previously valid cache entry."""

        cursor = self._connection.execute(
            """
            UPDATE inference_provider_capabilities
               SET last_error_code = ?, last_error = ?
             WHERE profile_id = ?
            """,
            (error_code, error_code, profile_id),
        )
        return cursor.rowcount == 1

    def remove(self, profile_id: str) -> bool:
        cursor = self._connection.execute(
            "DELETE FROM inference_profiles WHERE profile_id = ?",
            (profile_id,),
        )
        return cursor.rowcount == 1

    def bind_slot(
        self, memory_space_id: str, *, slot: str, profile_id: str
    ) -> str:
        if slot not in {"operational", "object_resolution", "background", "embedding"}:
            raise ValueError(
                "slot must be operational, object_resolution, background, or embedding"
            )
        if not profile_id.strip():
            raise ValueError("profile_id must not be empty")
        self._connection.execute(
            """
            INSERT INTO memory_space_model_profiles (
                memory_space_id, profile_slot, profile_id, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(memory_space_id, profile_slot) DO UPDATE SET
                profile_id = excluded.profile_id, updated_at = excluded.updated_at
            """,
            (memory_space_id, slot, profile_id, _now()),
        )
        return profile_id

    def get_slot(self, memory_space_id: str, slot: str) -> str | None:
        row = self._connection.execute(
            """
            SELECT profile_id FROM memory_space_model_profiles
            WHERE memory_space_id = ? AND profile_slot = ?
            """,
            (memory_space_id, slot),
        ).fetchone()
        return str(row["profile_id"]) if row is not None else None

    def list_slots(self, memory_space_id: str) -> dict[str, str]:
        rows = self._connection.execute(
            """
            SELECT profile_slot, profile_id FROM memory_space_model_profiles
            WHERE memory_space_id = ? ORDER BY profile_slot
            """,
            (memory_space_id,),
        ).fetchall()
        return {str(row["profile_slot"]): str(row["profile_id"]) for row in rows}

    def record_egress_audit(
        self,
        *,
        audit_id: str | None = None,
        memory_space_id: str | None,
        profile_id: str | None,
        operation: str,
        provider_kind: str,
        model: str,
        status: str,
        request_bytes: int = 0,
        response_bytes: int = 0,
        attempts: int = 0,
        error_code: str | None = None,
    ) -> str:
        resolved_audit_id = audit_id or str(uuid.uuid4())
        self._connection.execute(
            """
            INSERT INTO egress_audit (
                audit_id, memory_space_id, profile_id, operation, provider_kind,
                model, status, request_bytes, response_bytes, attempts, error_code, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_audit_id,
                memory_space_id,
                profile_id,
                operation,
                provider_kind,
                model,
                status,
                request_bytes,
                response_bytes,
                attempts,
                error_code,
                _now(),
            ),
        )
        return resolved_audit_id


class DatabaseBackedCapabilityStore:
    """Capability repository that opens a short-lived Local DB connection."""

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def get_capabilities(self, profile_id: str) -> ProviderCapabilities | None:
        from ..persistence import open_sqlite_connection
        from ..persistence import rounds_migrations as migrations

        connection = open_sqlite_connection(self._database_path)
        try:
            migrations.apply_migrations(connection)
            return InferenceProfileStore(connection).get_capabilities(profile_id)
        finally:
            connection.close()

    def list_capabilities(self) -> tuple[ProviderCapabilities, ...]:
        from ..persistence import open_sqlite_connection
        from ..persistence import rounds_migrations as migrations

        connection = open_sqlite_connection(self._database_path)
        try:
            migrations.apply_migrations(connection)
            return InferenceProfileStore(connection).list_capabilities()
        finally:
            connection.close()

    def get_capabilities_for_profile(
        self,
        profile: InferenceProfile,
        *,
        fresh_only: bool = False,
        now: str | None = None,
    ) -> ProviderCapabilities | None:
        from ..persistence import open_sqlite_connection
        from ..persistence import rounds_migrations as migrations

        connection = open_sqlite_connection(self._database_path)
        try:
            migrations.apply_migrations(connection)
            return InferenceProfileStore(connection).get_capabilities_for_profile(
                profile,
                fresh_only=fresh_only,
                now=now,
            )
        finally:
            connection.close()

    def upsert_capabilities(
        self, capabilities: ProviderCapabilities
    ) -> ProviderCapabilities:
        from ..persistence import open_sqlite_connection
        from ..persistence import rounds_migrations as migrations

        connection = open_sqlite_connection(self._database_path)
        try:
            migrations.apply_migrations(connection)
            result = InferenceProfileStore(connection).upsert_capabilities(capabilities)
            connection.commit()
            return result
        finally:
            connection.close()

    def invalidate_capabilities(self, profile_id: str, *, reason: str) -> bool:
        from ..persistence import open_sqlite_connection
        from ..persistence import rounds_migrations as migrations

        connection = open_sqlite_connection(self._database_path)
        try:
            migrations.apply_migrations(connection)
            changed = InferenceProfileStore(connection).invalidate_capabilities(
                profile_id,
                reason=reason,
            )
            connection.commit()
            return changed
        finally:
            connection.close()

    def record_capability_fallback(
        self,
        profile_id: str,
        *,
        failed_mode: StructuredOutputMode,
        successful_mode: StructuredOutputMode,
        error_code: str,
    ) -> bool:
        from ..persistence import open_sqlite_connection
        from ..persistence import rounds_migrations as migrations

        connection = open_sqlite_connection(self._database_path)
        try:
            migrations.apply_migrations(connection)
            changed = InferenceProfileStore(connection).record_capability_fallback(
                profile_id,
                failed_mode=failed_mode,
                successful_mode=successful_mode,
                error_code=error_code,
            )
            connection.commit()
            return changed
        finally:
            connection.close()

    def record_probe_error(self, profile_id: str, *, error_code: str) -> bool:
        from ..persistence import open_sqlite_connection
        from ..persistence import rounds_migrations as migrations

        connection = open_sqlite_connection(self._database_path)
        try:
            migrations.apply_migrations(connection)
            changed = InferenceProfileStore(connection).record_probe_error(
                profile_id,
                error_code=error_code,
            )
            connection.commit()
            return changed
        finally:
            connection.close()


__all__ = ["DatabaseBackedCapabilityStore", "InferenceProfileStore"]
