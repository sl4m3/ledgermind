"""Persistence package for Local-owned SQLite storage."""

from .contract_migration import (
    CONTRACT_MIGRATION_MARKER,
    ContractMigrationBackupError,
    ContractMigrationError,
    ContractMigrationPreconditionError,
    ContractMigrationResult,
    migrate_contract_payloads,
)
from .database import managed_connection, open_sqlite_connection
from .memory_space_repository import (
    MemorySpace,
    MemorySpaceSourceClientChangedError,
    SQLiteMemorySpaceRepository,
)
from .raw_round_repository import (
    CoreCommandRecord,
    CoreRawRoundDeliveryRecord,
    RawRoundRecord,
    SQLiteRawRoundRepository,
)
from .sqlite_uow import (
    SQLiteUnitOfWork,
    SQLiteUnitOfWorkError,
    SQLiteUnitOfWorkInactiveError,
)

__all__ = [
    "CONTRACT_MIGRATION_MARKER",
    "ContractMigrationBackupError",
    "ContractMigrationError",
    "ContractMigrationPreconditionError",
    "ContractMigrationResult",
    "CoreCommandRecord",
    "CoreRawRoundDeliveryRecord",
    "MemorySpace",
    "MemorySpaceSourceClientChangedError",
    "RawRoundRecord",
    "SQLiteMemorySpaceRepository",
    "SQLiteRawRoundRepository",
    "SQLiteUnitOfWork",
    "SQLiteUnitOfWorkError",
    "SQLiteUnitOfWorkInactiveError",
    "managed_connection",
    "migrate_contract_payloads",
    "open_sqlite_connection",
]
