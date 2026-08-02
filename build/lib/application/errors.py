"""Core application error hierarchy for LedgerMind."""

from __future__ import annotations


class LedgerMindError(RuntimeError):
    """Base type for deterministic domain/application failures."""


class ValidationError(ValueError, LedgerMindError):
    """Validation-related application/domain failure."""


class IdempotencyConflict(ValidationError):
    """Repeated request with a different request hash."""


class AtomAlreadySuperseded(ValidationError):
    """Attempted operation on a knowledge that is already superseded."""


class KnowledgeNotFound(ValidationError):
    """Requested knowledge is not found in current visibility."""


class AtomNotFound(ValidationError):
    """Requested atom is not found in current visibility."""


class MemorySpaceMismatch(ValidationError):
    """Requested object is outside the requested memory space."""


class ConcurrentModification(ValidationError):
    """Version mismatch or concurrent write conflict."""


class InvalidSupersession(ValidationError):
    """Invalid manual supersession input or state transition."""


class UnsupportedSchemaVersion(ValidationError):
    """Unsupported persisted or incoming schema version."""


class IntegrityViolation(ValidationError):
    """Command can not be applied because of invariant violation."""


class UnsupportedEvolutionDecision(ValidationError):
    """Policy returned an unsupported evolution decision type."""


# Compatibility aliases for existing module-level API.
class DeleteKnowledgeError(IntegrityViolation):
    """Backwards-compatible delete flow error."""


class SupersedeKnowledgeError(InvalidSupersession):
    """Backwards-compatible supersede flow error."""


__all__ = [
    "AtomAlreadySuperseded",
    "AtomNotFound",
    "ConcurrentModification",
    "DeleteKnowledgeError",
    "IdempotencyConflict",
    "IntegrityViolation",
    "InvalidSupersession",
    "KnowledgeNotFound",
    "LedgerMindError",
    "MemorySpaceMismatch",
    "SupersedeKnowledgeError",
    "UnsupportedEvolutionDecision",
    "UnsupportedSchemaVersion",
    "ValidationError",
]
