"""Deterministic identifier factory fake."""

from __future__ import annotations

from ledgermind_core.ports import IdentifierFactory


class FakeIdentifierFactory(IdentifierFactory):
    def __init__(self) -> None:
        self._atom_seq = 0
        self._knowledge_seq = 0
        self._revision_seq = 0
        self._event_seq = 0

    def new_atom_id(self) -> str:
        self._atom_seq += 1
        return f"atm_{self._atom_seq:06d}"

    def new_knowledge_id(self) -> str:
        self._knowledge_seq += 1
        return f"knw_{self._knowledge_seq:06d}"

    def new_revision_id(self) -> str:
        self._revision_seq += 1
        return f"rev_{self._revision_seq:06d}"

    def new_event_id(self) -> str:
        self._event_seq += 1
        return f"evt_{self._event_seq:06d}"
