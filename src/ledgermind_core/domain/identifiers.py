"""Typed identifier primitives used in domain contracts and repositories."""

from typing import NewType

AtomId = NewType("AtomId", str)
KnowledgeId = NewType("KnowledgeId", str)
MemorySpaceId = NewType("MemorySpaceId", str)
RevisionId = NewType("RevisionId", str)
EventId = NewType("EventId", str)

__all__ = ["AtomId", "KnowledgeId", "MemorySpaceId", "RevisionId", "EventId"]
