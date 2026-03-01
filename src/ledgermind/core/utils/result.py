"""
Result type for error-safe operations throughout LedgerMind.

Provides explicit success/failure handling with error codes and metadata.

Usage:
    result = store.append(event)
    if result.success:
        event_id = result.value
        print(f"Saved event {event_id}")
    else:
        handle_error(result.error, result.error_code)
        print(f"Failed: {result.error}")
"""
from dataclasses import dataclass
from typing import TypeVar, Generic, Optional, Any, Dict
from enum import Enum
import logging
import sqlite3

logger = logging.getLogger(__name__)

T = TypeVar('T')

class ErrorCode(str, Enum):
    """Standardized error codes for consistent error handling."""

    # === Validation Errors ===
    INVALID_INPUT = "INVALID_INPUT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CONSTRAINT_VIOLATION = "CONSTRAINT_VIOLATION"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"

    # === Storage Errors ===
    STORAGE_ERROR = "STORAGE_ERROR"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"
    NOT_FOUND = "NOT_FOUND"
    INTEGRITY_VIOLATION = "INTEGRITY_VIOLATION"

    # === Concurrency Errors ===
    LOCK_TIMEOUT = "LOCK_TIMEOUT"
    LOCK_ACQUISITION_FAILED = "LOCK_ACQUISITION_FAILED"
    CONFLICT = "CONFLICT"
    DEADLOCK_DETECTED = "DEADLOCK_DETECTED"

    # === System Errors ===
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INITIALIZATION_FAILED = "INITIALIZATION_FAILED"
    SHUTDOWN_ERROR = "SHUTDOWN_ERROR"
    UNAVAILABLE = "UNAVAILABLE"

    # === Security Errors ===
    PERMISSION_DENIED = "PERMISSION_DENIED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    FORBIDDEN = "FORBIDDEN"
    INTEGRITY_BREACH = "INTEGRITY_BREACH"

    # === External Service Errors ===
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"

    # === Model/ML Errors ===
    MODEL_NOT_LOADED = "MODEL_NOT_LOADED"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    MODEL_LOAD_TIMEOUT = "MODEL_LOAD_TIMEOUT"


@dataclass
class Result(Generic[T]):
    """
    Type-safe result container for all operations.

    Provides explicit success/failure handling with error details.

    Attributes:
        success (bool): True if operation succeeded, False otherwise
        value (Optional[T]): The result value (only if success=True)
        error (Optional[str]): Human-readable error message (only if success=False)
        error_code (Optional[ErrorCode]): Machine-readable error code
        metadata (Dict[str, Any]): Additional context about the operation

    Usage:
        result = store.append(event)
        if result:
            print("Operation succeeded!")
            event_id = result.value
        else:
            print(f"Operation failed: {result.error}")
            if result.error_code == ErrorCode.DUPLICATE_ENTRY:
                # Handle duplicate case...
    """

    success: bool
    value: Optional[T] = None
    error: Optional[str] = None
    error_code: Optional[ErrorCode] = None
    metadata: Dict[str, Any] = None

    def __bool__(self) -> bool:
        """Allows truthy checking: if result: ..."""
        return self.success

    def __iter__(self):
        """Allows unpacking: if value := result: ..."""
        yield self.success
        yield self.value

    @staticmethod
    def ok(value: T, metadata: Optional[Dict[str, Any]] = None) -> 'Result[T]':
        """
        Create a successful result.

        Args:
            value: The result value
            metadata: Optional additional context

        Returns:
            Result with success=True
        """
        return Result(
            success=True,
            value=value,
            metadata=metadata or {}
        )

    @staticmethod
    def fail(
        error: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        metadata: Optional[Dict[str, Any]] = None
    ) -> 'Result[T]':
        """
        Create a failed result.

        Args:
            error: Human-readable error message
            code: Machine-readable error code
            metadata: Optional additional context (IDs, params, etc.)

        Returns:
            Result with success=False
        """
        return Result(
            success=False,
            error=error,
            error_code=code,
            metadata=metadata or {}
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert Result to dictionary (useful for logging/JSON responses).
        """
        return {
            "success": self.success,
            "value": self.value,
            "error": self.error,
            "error_code": self.error_code.value if self.error_code else None,
            "metadata": self.metadata
        }


def safe_execute(
    func: callable,
    *args,
    **kwargs
) -> Result[Any]:
    """
    Execute function with automatic error conversion.

    Wraps any function and converts exceptions to Result objects.
    Provides consistent error handling across the codebase.

    Args:
        func: The function to execute
        *args, **kwargs: Arguments to pass to function

    Returns:
        Result with success/failure and appropriate error code

    Example:
        result = safe_execute(store.append, event)
        if not result:
            logger.error(f"Failed to append: {result.error}")
    """
    from ledgermind.core.core.exceptions import (
        ConflictError, InvariantViolation
    )

    try:
        value = func(*args, **kwargs)
        return Result.ok(value)

    except ValueError as e:
        return Result.fail(
            error=str(e),
            code=ErrorCode.VALIDATION_FAILED,
            metadata={"exception_type": "ValueError"}
        )

    except PermissionError as e:
        return Result.fail(
            error=str(e),
            code=ErrorCode.PERMISSION_DENIED,
            metadata={"exception_type": "PermissionError"}
        )

    except TimeoutError as e:
        return Result.fail(
            error=str(e),
            code=ErrorCode.LOCK_TIMEOUT,
            metadata={"exception_type": "TimeoutError"}
        )

    except ConflictError as e:
        return Result.fail(
            error=str(e),
            code=ErrorCode.CONFLICT,
            metadata={"exception_type": "ConflictError"}
        )

    except InvariantViolation as e:
        return Result.fail(
            error=str(e),
            code=ErrorCode.INTEGRITY_VIOLATION,
            metadata={"exception_type": "InvariantViolation"}
        )

    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e):
            return Result.fail(
                error=f"Duplicate entry: {e}",
                code=ErrorCode.DUPLICATE_ENTRY,
                metadata={"original_error": str(e)}
            )
        else:
            return Result.fail(
                error=f"Database integrity error: {e}",
                code=ErrorCode.STORAGE_ERROR,
                metadata={"original_error": str(e)}
            )

    except OSError as e:
        return Result.fail(
            error=f"File system error: {e}",
            code=ErrorCode.STORAGE_ERROR,
            metadata={"exception_type": "OSError", "errno": getattr(e, 'errno', None)}
        )

    except Exception as e:
        # Log unexpected errors with full traceback
        logger.exception(
            f"Unexpected error in {func.__name__}: {e}",
            extra={
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
        )

        return Result.fail(
            error=f"Internal error: {e}",
            code=ErrorCode.INTERNAL_ERROR,
            metadata={
                "exception_type": type(e).__name__,
                "original_error": str(e)
            }
        )


def unwrap_result(result: Result[T]) -> T:
    """
    Unwrap Result, raising exception if failed.

    Use this for migration or when Result isn't desired.

    Args:
        result: The result to unwrap

    Returns:
        The value if success

    Raises:
        RuntimeError: If result is failed
    """
    if result.success:
        return result.value
    else:
        raise RuntimeError(
            f"Operation failed: {result.error} "
            f"(code: {result.error_code})"
        )
