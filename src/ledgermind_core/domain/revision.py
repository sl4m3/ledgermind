"""Knowledge revision snapshot representation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .identifiers import AtomId, KnowledgeId, RevisionId


@dataclass(frozen=True, slots=True)
class KnowledgeRevision:
    revision_id: RevisionId
    knowledge_id: KnowledgeId
    version: int
    event_type: str
    snapshot_json: str
    cause_atom_id: AtomId | None
    created_at: datetime

    @classmethod
    def from_snapshot(
        cls,
        revision_id: RevisionId,
        knowledge_id: KnowledgeId,
        version: int,
        event_type: str,
        snapshot: Mapping[str, Any],
        cause_atom_id: AtomId | None,
        created_at: datetime,
    ) -> "KnowledgeRevision":
        snapshot_json = json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return cls(
            revision_id=revision_id,
            knowledge_id=knowledge_id,
            version=version,
            event_type=event_type,
            snapshot_json=snapshot_json,
            cause_atom_id=cause_atom_id,
            created_at=created_at,
        )

    @property
    def snapshot(self) -> dict[str, Any]:
        return json.loads(self.snapshot_json)

    def __post_init__(self) -> None:
        if not self.revision_id:
            raise ValueError("revision_id must not be empty")
        if not self.knowledge_id:
            raise ValueError("knowledge_id must not be empty")
        if self.version < 1:
            raise ValueError("version must be >= 1")
        if not self.event_type.strip():
            raise ValueError("event_type must not be empty")
        if not self.snapshot_json.strip():
            raise ValueError("snapshot_json must not be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

        try:
            snapshot = json.loads(self.snapshot_json)
        except ValueError as exc:
            raise ValueError("snapshot_json must be valid JSON") from exc

        object.__setattr__(
            self,
            "snapshot_json",
            json.dumps(
                snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )


__all__ = ["KnowledgeRevision"]
