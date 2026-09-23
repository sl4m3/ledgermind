"""Reusable production-local test support shared by certification harnesses.

The helpers in this module deliberately keep the production topology intact:
Local owns the databases and starts the signed Core process.  They are test
support only; no production request path imports this module.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import (
    CoreSecurityConfig,
    EmbeddingConfig,
    LocalConfig,
    ProfileSlotsConfig,
    WorkerConfig,
    WorkerSetConfig,
)
from .inference.profile_slots import (
    DatabaseBackedProfileResolver,
    ProfileSlot,
)
from .inference.profile_store import (
    DatabaseBackedCapabilityStore,
    InferenceProfileStore,
)
from .inference.profiles import (
    DEFAULT_GENERATION_MAX_INPUT_TOKENS,
    InferenceProfile,
)
from .inference.provider_probe import ProviderProbe
from .inference.secrets import SecretStore
from .paths import ServicePaths
from .persistence import open_sqlite_connection, rounds_migrations


class ProductionSupportError(RuntimeError):
    """A bounded failure while preparing or observing production-local."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def background_structured_output_preference(
    configured_output_modes: tuple[str, ...],
) -> str:
    """Choose a deterministic structured transport for optional background work.

    JSON Schema is preferred when the profile advertises it because the
    background capability probe must survive a process restart without
    depending on a provider's looser ``json_object`` formatting behavior.
    The remaining modes are kept as explicit compatibility fallbacks.
    """

    if "strict_json_schema" in configured_output_modes:
        return "strict_json_schema"
    if "json_schema" in configured_output_modes:
        return "json_schema"
    if "json_object" in configured_output_modes:
        return "json_object"
    if "prompt_only" in configured_output_modes:
        return "prompt_only"
    return "auto"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def copy_signed_core(binary: Path, paths: ServicePaths) -> None:
    """Install one signed Core binary into Local's private runtime directory."""

    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ProductionSupportError(
            f"real Core binary is missing or not executable: {binary}"
        )
    target = paths.core_data_dir / "bin" / "ledgermind-core"
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    shutil.copy2(binary, target)
    os.chmod(target, 0o700)
    private_key = Ed25519PrivateKey.generate()
    target.with_suffix(".sig").write_bytes(private_key.sign(target.read_bytes()))
    target.with_suffix(".pub").write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    )


def _generation_for_task(lab_config: Any, task_kind: str) -> Any:
    """Resolve the Lab task route without inventing a production fallback."""

    profile_name = lab_config.generation_profile_for_task(task_kind)
    return lab_config.with_profiles(generation_profile=profile_name).generation


def config_for(*, home: Path, lab_config: Any, port: int) -> LocalConfig:
    """Build the same secure Local configuration used by pre-production gates."""

    embedding = lab_config.embedding
    return LocalConfig(
        config_version=2,
        semantic_language=lab_config.semantic_language,
        bind_host="127.0.0.1",
        bind_port=port,
        rounds_database_path="rounds.db",
        knowledge_database_path="knowledge.db",
        core_backend="process",
        core_binary_path="bin/ledgermind-core",
        core_signature_path="bin/ledgermind-core.sig",
        core_public_key_path="bin/ledgermind-core.pub",
        verify_core_signature=True,
        core_startup_timeout_seconds=30.0,
        core_request_timeout_seconds=120.0,
        core_security=CoreSecurityConfig(
            profile="secure",
            require_network_isolation=True,
            require_rounds_database_hidden=True,
            require_filesystem_allowlist=True,
            require_environment_sanitized=True,
            require_signature=True,
        ),
        workers=WorkerSetConfig(
            retention=WorkerConfig(enabled=True, interval_seconds=300.0),
            core_commands=WorkerConfig(enabled=True, interval_seconds=0.2),
            core_model_tasks=WorkerConfig(enabled=True, interval_seconds=0.2),
        ),
        worker_max_attempts=3,
        worker_retry_delay_seconds=1.0,
        worker_lease_seconds=420.0,
        generation_concurrency=1,
        provider_capability_ttl_seconds=86_400,
        inference_secrets_path=str(home / "secrets.json"),
        profile_slots=ProfileSlotsConfig(
            operational="generation-operational",
            object_resolution="generation-object-resolution",
            background="generation-background",
            embedding="embedding-api",
        ),
        embedding=EmbeddingConfig(
            enabled=True,
            provider_mode="api",
            endpoint=embedding.endpoint,
            model=embedding.model,
            dimensions=embedding.dimensions or 2048,
            batch_size=embedding.batch_size,
            max_concurrency=embedding.max_concurrency,
            max_wait_seconds=embedding.max_wait_seconds,
            timeout_seconds=min(embedding.timeout_seconds, 120.0),
            secret_ref="embedding-api",
        ),
    )


def seed_local(
    *,
    paths: ServicePaths,
    config: LocalConfig,
    lab_config: Any,
    memory_space_id: str,
    source_client: str = "hermes-production-local",
) -> None:
    """Create the migration-owned seed state and bind all inference slots."""

    generation = _generation_for_task(lab_config, "round_semantic")
    object_resolution_generation = _generation_for_task(
        lab_config, "object_resolution"
    )
    background_generation = _generation_for_task(lab_config, "execution_semantic")
    embedding = lab_config.embedding
    configured_output_modes = tuple(generation.structured_output_modes)
    background_output_preference = background_structured_output_preference(
        configured_output_modes
    )
    secret_store = SecretStore(paths.home / "secrets.json")
    secret_store.put("generation-api", generation.token.get_secret_value())
    secret_store.put(
        "generation-object-resolution-api",
        object_resolution_generation.token.get_secret_value(),
    )
    secret_store.put("embedding-api", embedding.token.get_secret_value())
    database = paths.resolve_rounds_database_path(config.rounds_database_path)
    connection = open_sqlite_connection(database)
    try:
        rounds_migrations.apply_migrations(connection)
        now = utc_now()
        connection.execute(
            """
            INSERT INTO memory_spaces(memory_space_id, source_client, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(memory_space_id) DO NOTHING
            """,
            (memory_space_id, source_client, now, now),
        )
        store = InferenceProfileStore(connection)
        for profile_id, slot, selected_generation, secret_ref in (
            ("generation-operational", "operational", generation, "generation-api"),
            (
                "generation-object-resolution",
                "object_resolution",
                object_resolution_generation,
                "generation-object-resolution-api",
            ),
            ("generation-background", "background", background_generation, "generation-api"),
        ):
            reasoning_profile = selected_generation.reasoning.for_provider_model(
                selected_generation.provider,
                selected_generation.model,
            )
            generation_extra_body = dict(reasoning_profile.extra_body)
            if (
                reasoning_profile.reasoning_effort is not None
                and "reasoning_effort" not in generation_extra_body
            ):
                generation_extra_body["reasoning_effort"] = reasoning_profile.reasoning_effort
            store.upsert(
                InferenceProfile(
                    profile_id=profile_id,
                    provider_kind=(
                        "nvidia_nim"
                        if selected_generation.provider == "nvidia"
                        else "openai_compatible"
                    ),
                    base_url=selected_generation.endpoint,
                    model=selected_generation.model,
                    secret_ref=secret_ref,
                    timeout_seconds=min(selected_generation.timeout_seconds, 300.0),
                    max_retries=selected_generation.max_retries,
                    max_input_tokens=DEFAULT_GENERATION_MAX_INPUT_TOKENS,
                    max_output_tokens=selected_generation.max_output_tokens,
                    extra_body=generation_extra_body,
                    # Keep operational work capability-aware, while the
                    # optional background path uses the most reliable
                    # configured JSON transport. Both paths still pass
                    # through the same closed Core contract and validation
                    # layer.
                    structured_output_preference=(
                        background_output_preference
                        if slot == "background"
                        else "auto"
                    ),
                    token_parameter="max_tokens",
                    supports_system_role=True,
                    supports_seed=False,
                )
            )
            store.bind_slot(memory_space_id, slot=slot, profile_id=profile_id)
        store.upsert(
            InferenceProfile(
                profile_id="embedding-api",
                base_url=embedding.endpoint,
                model=embedding.model,
                secret_ref="embedding-api",
                timeout_seconds=min(embedding.timeout_seconds, 120.0),
                max_retries=embedding.max_retries,
                max_input_tokens=12_000,
                max_output_tokens=2_000,
            )
        )
        store.bind_slot(memory_space_id, slot="embedding", profile_id="embedding-api")
        connection.commit()
    finally:
        connection.close()


def probe_generation_profiles(
    *, paths: ServicePaths, database: Path, memory_space_id: str
) -> dict[str, Any]:
    """Warm all three generation-slot capability rows using the actual provider."""

    resolver = DatabaseBackedProfileResolver(database)
    probe = ProviderProbe(
        profile_resolver=resolver,
        secret_store=SecretStore(paths.home / "secrets.json"),
        capability_store=DatabaseBackedCapabilityStore(str(database)),
        capability_ttl_seconds=86_400,
    )
    results: dict[str, Any] = {}
    for slot in (
        ProfileSlot.OPERATIONAL,
        ProfileSlot.OBJECT_RESOLUTION,
        ProfileSlot.BACKGROUND,
    ):
        result = probe.probe(memory_space_id, slot, force=False, reprobe=False)
        results[slot.value] = {
            "status": result.status,
            "selected_mode": result.selected_mode,
            "cache_hit": bool(result.metadata.get("cache_hit", False)),
            "profile_fingerprint": result.capabilities.profile_fingerprint,
            "probe_result": result.capabilities.probe_result,
            "error_code": result.error_code,
        }
    return results


def http_json(
    base_url: str,
    path: str,
    *,
    token: str,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    """Call the loopback Local API without logging credentials or payloads."""

    body = (
        None
        if payload is None
        else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    headers = {"accept": "application/json", "authorization": f"Bearer {token}"}
    if body is not None:
        headers["content-type"] = "application/json"
    request = urllib_request.Request(
        base_url + path, data=body, headers=headers, method=method
    )
    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            status = response.status
            raw = response.read().decode("utf-8")
    except urllib_error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except urllib_error.URLError as exc:
        return 0, {"error": "local_unreachable", "detail": str(exc.reason)[:200]}
    try:
        decoded = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        decoded = {"error": "non_json_response"}
    return status, decoded if isinstance(decoded, dict) else {"value": decoded}


def wait_until(
    predicate: Callable[[], bool], *, timeout: float, interval: float = 1.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    if not predicate():
        raise ProductionSupportError("timeout waiting for production Local/Core queue")


def start_local(
    *, home: Path, port: int, env: Mapping[str, str], log_path: Path
) -> subprocess.Popen[bytes]:
    command = [
        sys.executable,
        "-m",
        "ledgermind_local.cli",
        "--home",
        str(home),
        "serve",
        "--port",
        str(port),
    ]
    log_handle = log_path.open("wb")
    process = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[2],
        env=dict(env),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    log_handle.close()
    return process


def terminate(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


__all__ = [
    "ProductionSupportError",
    "config_for",
    "copy_signed_core",
    "free_port",
    "http_json",
    "probe_generation_profiles",
    "seed_local",
    "start_local",
    "terminate",
    "utc_now",
    "wait_until",
]
