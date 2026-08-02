"""In-memory fake repository implementations used by core tests."""

from __future__ import annotations

import copy
from typing import Iterable, Mapping, Sequence

from domain import Atom, KnowledgeEvidence, KnowledgeItem, KnowledgeRevision
from ports import (
    AtomRepository,
    EvidenceRepository,
    IdempotencyRepository,
    KnowledgeRepository,
    RevisionRepository,
    StoredIdempotencyResult,
)


class _TransactionalRepo:
    def __init__(
        self,
        source: Mapping,
        fail_steps: Iterable[str] | None = None,
        namespace: str = "",
    ):
        self._namespace = namespace
        self._fail_steps = set(fail_steps or [])
        self._committed = copy.deepcopy(source)
        self._staged = copy.deepcopy(source)

    def _fail(self, step: str) -> None:
        if step in self._fail_steps or f"{self._namespace}.{step}" in self._fail_steps:
            raise RuntimeError(f"fake repository step failed: {self._namespace}.{step}")

    def begin(self) -> None:
        self._staged = copy.deepcopy(self._committed)

    def commit(self) -> None:
        self._committed = copy.deepcopy(self._staged)

    def rollback(self) -> None:
        self._staged = copy.deepcopy(self._committed)

    def committed(self):
        return copy.deepcopy(self._committed)


class FakeAtomRepository(_TransactionalRepo, AtomRepository):
    def __init__(self, seed: Mapping[str, Mapping[str, Atom]] | None = None, fail_steps=None):
        super().__init__(source=copy.deepcopy(seed or {}), fail_steps=fail_steps, namespace="atom")

    def get(self, memory_space_id: str, atom_id: str) -> Atom | None:
        self._fail("get")
        return self._staged.get(memory_space_id, {}).get(atom_id)

    def find_by_source_version(
        self,
        memory_space_id: str,
        source_round_key: str,
        prompt_version: int,
        schema_version: int,
    ) -> Atom | None:
        self._fail("find_by_source_version")
        for atom in self._staged.get(memory_space_id, {}).values():
            if atom.source.source_round_id == source_round_key:
                if (
                    atom.extraction.prompt_version == prompt_version
                    and atom.extraction.schema_version == schema_version
                ):
                    return atom
        return None

    def add(self, atom: Atom) -> None:
        self._fail("add")
        self._staged.setdefault(atom.memory_space_id, {})
        self._staged[atom.memory_space_id][atom.atom_id] = atom


class FakeKnowledgeRepository(_TransactionalRepo, KnowledgeRepository):
    def __init__(self, seed: Mapping[str, Mapping[str, KnowledgeItem]] | None = None, fail_steps=None):
        super().__init__(source=copy.deepcopy(seed or {}), fail_steps=fail_steps, namespace="knowledge")

    def get(self, memory_space_id: str, knowledge_id: str) -> KnowledgeItem | None:
        self._fail("get")
        return self._staged.get(memory_space_id, {}).get(knowledge_id)

    def add(self, item: KnowledgeItem) -> None:
        self._fail("add")
        self._staged.setdefault(item.memory_space_id, {})
        self._staged[item.memory_space_id][item.knowledge_id] = item

    def update(self, item: KnowledgeItem, expected_version: int) -> None:
        self._fail("update")
        current = self.get(item.memory_space_id, item.knowledge_id)
        if current is None or current.version != expected_version:
            raise RuntimeError("version mismatch")
        self._staged[item.memory_space_id][item.knowledge_id] = item

    def get_many(self, memory_space_id: str, knowledge_ids: tuple[str, ...]) -> list[KnowledgeItem]:
        self._fail("get_many")
        items: list[KnowledgeItem] = []
        bucket = self._staged.get(memory_space_id, {})
        for knowledge_id in knowledge_ids:
            item = bucket.get(knowledge_id)
            if item is not None:
                items.append(item)
        return items


class FakeEvidenceRepository(_TransactionalRepo, EvidenceRepository):
    def __init__(self, seed: Sequence[KnowledgeEvidence] | None = None, fail_steps=None):
        super().__init__(source=list(seed or []), fail_steps=fail_steps, namespace="evidence")

    def add(self, link: KnowledgeEvidence) -> None:
        self._fail("add")
        self._staged.append(link)

    def count_for_knowledge(self, memory_space_id: str, knowledge_id: str) -> int:
        self._fail("count_for_knowledge")
        return len([link for link in self._staged if link.knowledge_id == knowledge_id])

    def list_atom_ids(self, memory_space_id: str, knowledge_id: str) -> list[str]:
        self._fail("list_atom_ids")
        return [link.atom_id for link in self._staged if link.knowledge_id == knowledge_id]


class FakeRevisionRepository(_TransactionalRepo, RevisionRepository):
    def __init__(self, seed: Sequence[KnowledgeRevision] | None = None, fail_steps=None):
        super().__init__(source=list(seed or []), fail_steps=fail_steps, namespace="revision")

    def add(self, item: KnowledgeRevision) -> None:
        self._fail("add")
        self._staged.append(item)

    def list_for_knowledge(
        self,
        memory_space_id: str,
        knowledge_id: str,
    ) -> list[KnowledgeRevision]:
        self._fail("list_for_knowledge")
        return [
            revision
            for revision in self._staged
            if revision.knowledge_id == knowledge_id
        ]


class FakeIdempotencyRepository(_TransactionalRepo, IdempotencyRepository):
    def __init__(self, seed: Mapping[str, StoredIdempotencyResult] | None = None, fail_steps=None):
        super().__init__(source=dict(seed or {}), fail_steps=fail_steps, namespace="idempotency")

    def get(self, key: str) -> StoredIdempotencyResult | None:
        self._fail("get")
        return self._staged.get(key)

    def add(self, result: StoredIdempotencyResult) -> None:
        self._fail("add")
        self._staged[result.key] = result
