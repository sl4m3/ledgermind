"""Configure provider profiles without installing a target automatically."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ledgermind_local.runtime.supervisor import RuntimeSupervisor

from ..config_writer import (
    persist_generation_probe,
    resolve_provider_tokens,
    resolve_reranker_token,
    write_installer_config,
    write_local_config,
    write_local_profiles,
)
from ..models import InstallerConfig
from ..paths import InstallerPaths
from ..profiles.probes import probe_embedding_api, probe_generation


def configure(
    *,
    config: InstallerConfig,
    paths: InstallerPaths,
    validate_providers: bool = False,
    generation_stdin: str | None = None,
    embedding_stdin: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    probes: dict[str, Any] = {}
    if validate_providers:
        generation_token, embedding_token = resolve_provider_tokens(
            config,
            paths,
            generation_stdin=generation_stdin,
            embedding_stdin=embedding_stdin,
        )
        probes["generation"] = probe_generation(
            config.generation, token=generation_token
        )
        if config.embedding.mode == "api" and config.embedding.api is not None:
            assert embedding_token is not None
            probes["embedding"] = probe_embedding_api(
                config.embedding.api, token=embedding_token
            )
        if config.reranker.mode == "api" and config.reranker.api is not None:
            from ledgermind_local.inference.retrieval_reranker import ApiReranker

            reranker_token = resolve_reranker_token(config, paths)
            assert reranker_token is not None
            scorer = ApiReranker(
                config.reranker.api.endpoint,
                reranker_token,
                config.reranker.api.model,
                timeout_seconds=config.reranker.api.timeout_seconds,
            )
            scores = scorer.score("configuration check", ["configuration check"])
            if len(scores) != 1:
                raise ValueError("incomplete reranker API smoke response")
            probes["reranker"] = {"status": "passed"}
    if dry_run:
        return {"status": "dry_run", "probes": probes}
    # A provider reconfiguration is explicit, but it must not race a live
    # worker that still holds the previous profile cache.
    RuntimeSupervisor(paths).stop(force=True)
    mutable_files = (
        paths.config_file,
        paths.profiles_file,
        paths.secrets_file,
        paths.config_dir / "local-config.json",
        paths.data_dir / "local" / "config.json",
    )
    backups = {
        path: (
            path.is_file(),
            path.read_bytes() if path.is_file() else b"",
            path.stat().st_mode & 0o777 if path.is_file() else 0o600,
        )
        for path in mutable_files
    }
    database = paths.memory_data_dir / "rounds.db"
    database_files = (
        database,
        database.with_name("rounds.db-wal"),
        database.with_name("rounds.db-shm"),
    )
    paths.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(
        prefix=".configure-rollback-", dir=paths.state_dir
    ) as temporary_name:
        rollback_dir = Path(temporary_name)
        database_backups: dict[Path, tuple[bool, Path | None]] = {}
        for index, path in enumerate(database_files):
            if path.is_file():
                destination = rollback_dir / f"database-{index}"
                shutil.copy2(path, destination)
                database_backups[path] = (True, destination)
            else:
                database_backups[path] = (False, None)
        try:
            metadata = write_installer_config(
                config,
                paths,
                generation_stdin=generation_stdin,
                embedding_stdin=embedding_stdin,
            )
            metadata["local_config"] = str(write_local_config(config, paths))
            metadata["local_profiles"] = write_local_profiles(config, paths)
            if validate_providers:
                metadata["generation_capabilities"] = persist_generation_probe(
                    config, paths, probes["generation"]
                )
        except Exception:
            for path, (existed, content, mode) in backups.items():
                if existed:
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    path.write_bytes(content)
                    os.chmod(path, mode)
                else:
                    path.unlink(missing_ok=True)
            for path, (existed, backup) in database_backups.items():
                if existed and backup is not None:
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    shutil.copy2(backup, path)
                else:
                    path.unlink(missing_ok=True)
            raise
    generation_status = probes.get("generation", {}).get(
        "status", "configured-not-probed"
    )
    generation_route = " -> ".join(
        item
        for item in (config.generation.route, *config.generation.fallback_routes)
        if item
    )
    generation_readiness = f"{generation_status}; model={config.generation.model}" + (
        f"; route={generation_route}" if generation_route else ""
    )
    if config.embedding.mode == "api":
        assert config.embedding.api is not None
        embedding_status = probes.get("embedding", {}).get(
            "status", "configured-not-probed"
        )
        embedding_readiness = (
            f"{embedding_status}; model={config.embedding.api.model}; "
            f"dimensions={config.embedding.api.dimensions}"
        )
    else:
        assert config.embedding.local is not None
        embedding_readiness = (
            f"local-configured; model={config.embedding.local.catalog_id}"
        )
    return {
        "status": "success",
        "config": metadata,
        "probes": probes,
        "readiness": {
            "platform": "linux",
            "core": "restart-on-next-agent-use",
            "generation": generation_readiness,
            "embeddings": embedding_readiness,
            "reranker": (
                f"api-ready; model={config.reranker.api.model}"
                if config.reranker.api is not None
                else (
                    f"local-configured; device={config.reranker.device}"
                    if config.reranker.mode == "local"
                    else "disabled; Core ranking"
                )
            ),
            "agents": f"{len(config.integrations)} preserved",
            "memory_mode": config.memory_mode,
        },
    }


__all__ = ["configure"]
