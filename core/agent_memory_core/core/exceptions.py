class AgentMemoryError(Exception):
    """Base class for all agent-memory errors."""
    pass

class InvariantViolation(AgentMemoryError):
    """Raised when an architectural invariant is violated."""
    pass

class ConflictError(InvariantViolation):
    """Raised when a conflict invariant (I4) is violated."""
    pass
