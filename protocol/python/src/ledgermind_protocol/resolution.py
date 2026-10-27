"""Shared, non-semantic Hermes resolution identity mapping."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .models import LedgerMindResolution

Metadata = Mapping[str, Any] | Sequence[Mapping[str, Any]]


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _metadata_sources(value: Metadata | None) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        sources: list[Mapping[str, Any]] = [value]
        for key in ("resolution", "resolution_metadata", "metadata", "session_metadata"):
            nested = value.get(key)
            if isinstance(nested, Mapping):
                sources.append(nested)
        return sources
    return [item for item in value if isinstance(item, Mapping)]


def _first_text(sources: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> str | None:
    for source in sources:
        for key in keys:
            value = _text(source.get(key))
            if value is not None:
                return value
    return None


def _all_text(sources: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for source in sources:
        for key in keys:
            value = _text(source.get(key))
            if value is not None and value not in seen:
                seen.add(value)
                values.append(value)
    return values


def _path(value: str | None, *, base_path: str | Path | None = None) -> Path | None:
    if value is None:
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute() and base_path is not None:
        candidate = Path(base_path).expanduser() / candidate
    return candidate.resolve()


def find_git_root(path: str | Path | None) -> Path | None:
    """Return the nearest git root for a working directory or file path."""

    if path is None:
        return None
    candidate = Path(path).expanduser().resolve()
    if candidate.exists() and candidate.is_file():
        candidate = candidate.parent
    for directory in (candidate, *candidate.parents):
        if (directory / ".git").exists():
            return directory
    return None


def _mapping_entry(
    root: Path | None,
    repository_mapping: Mapping[str, object] | None,
    *,
    base_path: str | Path | None = None,
) -> Mapping[str, Any] | None:
    if root is None or repository_mapping is None:
        return None
    normalized_root = root.resolve()
    for raw_key, raw_value in repository_mapping.items():
        if not isinstance(raw_key, str):
            continue
        try:
            candidate_path = Path(raw_key).expanduser()
            if not candidate_path.is_absolute() and base_path is not None:
                candidate_path = Path(base_path).expanduser() / candidate_path
            candidate = candidate_path.resolve()
        except OSError:
            continue
        if candidate != normalized_root:
            continue
        if isinstance(raw_value, Mapping):
            return raw_value
        if isinstance(raw_value, str):
            return {"repository_id": raw_value}
    return None


def resolve_hermes_resolution(
    session_id: str,
    *,
    metadata: Metadata | None = None,
    project_id: str | None = None,
    repository_id: str | None = None,
    task_id: str | None = None,
    working_directory: str | None = None,
    repository_root: str | None = None,
    repository_mapping: Mapping[str, object] | None = None,
    base_path: str | Path | None = None,
) -> LedgerMindResolution:
    """Map explicit Hermes/session metadata to the canonical resolution model.

    Project and task identifiers are never inferred from path names or round
    identifiers.  The session identifier is the only conversation fallback.
    """

    normalized_session_id = _text(session_id)
    if normalized_session_id is None:
        raise ValueError("session_id must be a non-empty string")

    sources = _metadata_sources(metadata)
    resolved_project = _text(project_id) or _first_text(sources, ("project_id", "project"))
    resolved_repository = _text(repository_id) or _first_text(
        sources, ("repository_id", "repository", "repo_id", "repo")
    )
    resolved_task = _text(task_id) or _first_text(sources, ("task_id", "task"))

    configured_root = _text(repository_root)
    metadata_roots = _all_text(sources, ("repository_root", "git_root"))
    configured_working_directory = _text(working_directory)
    metadata_working_directories = _all_text(sources, ("working_directory", "cwd", "workdir"))
    root: Path | None = None
    if configured_root is not None:
        root = _path(configured_root, base_path=base_path)
    elif len(metadata_roots) == 1:
        root = _path(metadata_roots[0], base_path=base_path)
    elif not metadata_roots:
        working_directories = (
            [configured_working_directory]
            if configured_working_directory is not None
            else metadata_working_directories
        )
        roots = {
            git_root
            for git_root in (
                find_git_root(_path(value, base_path=base_path))
                for value in working_directories
            )
            if git_root is not None
        }
        if len(roots) == 1:
            root = next(iter(roots))

    mapping_entry = _mapping_entry(root, repository_mapping, base_path=base_path)
    if mapping_entry is not None:
        if resolved_repository is None:
            resolved_repository = _text(
                mapping_entry.get("repository_id")
                or mapping_entry.get("repository")
            )
        if resolved_project is None:
            resolved_project = _text(mapping_entry.get("project_id") or mapping_entry.get("project"))

    if resolved_repository is None and root is not None:
        resolved_repository = root.as_posix()

    return LedgerMindResolution(
        schema_version=1,
        project_id=resolved_project,
        repository_id=resolved_repository,
        task_id=resolved_task,
        conversation_id=normalized_session_id,
    )


def build_resolution_extension(
    session_id: str,
    **kwargs: Any,
) -> dict[str, object]:
    """Return a JSON-ready canonical extension payload with explicit nulls."""

    return resolve_hermes_resolution(session_id, **kwargs).model_dump(mode="json")


__all__ = [
    "LedgerMindResolution",
    "build_resolution_extension",
    "find_git_root",
    "resolve_hermes_resolution",
]
