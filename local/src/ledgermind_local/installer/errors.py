"""Stable installer errors and exit codes."""

from __future__ import annotations

from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    SUCCESS = 0
    INVALID_ARGUMENTS = 2
    UNSUPPORTED_PLATFORM = 3
    PREFLIGHT_FAILED = 4
    DOWNLOAD_FAILED = 5
    SIGNATURE_FAILED = 6
    CONFIGURATION_INVALID = 7
    PROVIDER_PROBE_FAILED = 8
    ADAPTER_FAILED = 9
    TRANSACTION_FAILED = 10
    DOCTOR_FAILED = 11
    UPDATE_ROLLBACK = 12
    RUNTIME_FAILED = 13
    PERMISSION_ERROR = 14
    USER_CANCELLED = 15


class InstallerError(RuntimeError):
    """Base error carrying a machine-stable code and exit status."""

    exit_code = ExitCode.TRANSACTION_FAILED
    error_code = "installer_error"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.details = details


class InvalidArgumentsError(InstallerError):
    exit_code = ExitCode.INVALID_ARGUMENTS
    error_code = "invalid_arguments"


class UnsupportedPlatformError(InstallerError):
    exit_code = ExitCode.UNSUPPORTED_PLATFORM
    error_code = "unsupported_platform"


class PreflightError(InstallerError):
    exit_code = ExitCode.PREFLIGHT_FAILED
    error_code = "preflight_failed"


class DownloadError(InstallerError):
    exit_code = ExitCode.DOWNLOAD_FAILED
    error_code = "download_failed"


class SignatureVerificationError(InstallerError):
    exit_code = ExitCode.SIGNATURE_FAILED
    error_code = "signature_verification_failed"


class ConfigurationError(InstallerError):
    exit_code = ExitCode.CONFIGURATION_INVALID
    error_code = "configuration_invalid"


class ProviderProbeError(InstallerError):
    exit_code = ExitCode.PROVIDER_PROBE_FAILED
    error_code = "provider_probe_failed"


class AdapterError(InstallerError):
    exit_code = ExitCode.ADAPTER_FAILED
    error_code = "integration_adapter_failed"


class TransactionError(InstallerError):
    exit_code = ExitCode.TRANSACTION_FAILED
    error_code = "installation_transaction_failed"


class DoctorError(InstallerError):
    exit_code = ExitCode.DOCTOR_FAILED
    error_code = "doctor_failed"


class UpdateRollbackError(InstallerError):
    exit_code = ExitCode.UPDATE_ROLLBACK
    error_code = "update_rollback"


class RuntimeLifecycleError(InstallerError):
    exit_code = ExitCode.RUNTIME_FAILED
    error_code = "runtime_lifecycle_failed"


class PermissionInstallerError(InstallerError):
    exit_code = ExitCode.PERMISSION_ERROR
    error_code = "permission_error"


class UserCancelledError(InstallerError):
    exit_code = ExitCode.USER_CANCELLED
    error_code = "user_cancelled"


__all__ = [
    "AdapterError",
    "ConfigurationError",
    "DoctorError",
    "DownloadError",
    "ExitCode",
    "InstallerError",
    "InvalidArgumentsError",
    "PermissionInstallerError",
    "PreflightError",
    "ProviderProbeError",
    "RuntimeLifecycleError",
    "SignatureVerificationError",
    "TransactionError",
    "UnsupportedPlatformError",
    "UpdateRollbackError",
    "UserCancelledError",
]
