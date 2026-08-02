"""Atom read use case for LedgerMind core."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ledgermind_core.domain import Atom
from ledgermind_core.ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class GetAtomQuery:
    memory_space_id: str
    atom_id: str

    def __post_init__(self) -> None:
        if not self.memory_space_id:
            raise ValueError("memory_space_id must not be empty")
        if not self.atom_id:
            raise ValueError("atom_id must not be empty")


class GetAtomHandler:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def handle(self, query: GetAtomQuery) -> Atom | None:
        with self._uow_factory() as uow:
            return uow.atoms.get(query.memory_space_id, query.atom_id)


__all__ = [
    "GetAtomHandler",
    "GetAtomQuery",
]
