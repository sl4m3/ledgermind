class LedgermindError(Exception):
    """Base class for all ledgermind errors."""
    pass

class InvariantViolation(LedgermindError):
    """Raised when an architectural invariant is violated."""
    pass

class ConflictError(InvariantViolation):
    """Raised when a conflict invariant (I4) is violated."""
    pass
