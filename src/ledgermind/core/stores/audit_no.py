import logging
from typing import List, Dict, Any, Optional
from ledgermind.core.stores.interfaces import AuditProvider

logger = logging.getLogger("ledgermind-core.audit-no")

class NoAuditProvider(AuditProvider):
    """
    A fallback AuditProvider that doesn't use Git.
    Suitable for environments without Git installed.
    Only provides basic filesystem operations without versioning.
    """
    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def initialize(self):
        logger.info("Initializing NoAuditProvider (Git fallback mode)")

    def add_artifact(self, relative_path: str, content: str, commit_msg: str):
        logger.debug(f"Audit (No-Op): Adding {relative_path}")

    def update_artifact(self, relative_path: str, content: str, commit_msg: str):
        logger.debug(f"Audit (No-Op): Updating {relative_path}")

    def get_head_hash(self) -> Optional[str]:
        return "no-git"

    def purge_artifact(self, relative_path: str):
        logger.debug(f"Audit (No-Op): Purging {relative_path}")

    def commit_transaction(self, message: str):
        pass

    def get_history(self, relative_path: str) -> List[Dict[str, Any]]:
        return []

    def run(self, args: List[str]):
        """No-Op for git commands."""
        logger.debug(f"Audit (No-Op): Bypassing Git command: {' '.join(args)}")
        return None
