"""Universal, transaction-safe LedgerMind installer.

The installer package deliberately owns configuration and release lifecycle
contracts.  Runtime and target implementations depend on these contracts,
not on the command line parser, so interactive and agent-driven installs use
the same code path.
"""

from .errors import ExitCode, InstallerError
from .models import InstallerConfig
from .result import InstallResult

__all__ = ["ExitCode", "InstallResult", "InstallerConfig", "InstallerError"]
