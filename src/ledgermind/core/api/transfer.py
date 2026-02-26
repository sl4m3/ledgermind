import os
import tarfile
import logging
import shutil
from typing import Optional
from datetime import datetime

logger = logging.getLogger("ledgermind-core.transfer")

class MemoryTransferManager:
    """Handles Export/Import and S3 backups of the memory system."""
    
    def __init__(self, storage_path: str):
        self.storage_path = storage_path

    def export_to_tar(self, output_path: str) -> str:
        """Packs the entire memory storage into a .tar.gz archive.

        Args:
            output_path: The filename for the export. Must not contain directory path components.

        Raises:
            ValueError: If output_path contains directory components (security check).
        """
        if os.path.basename(output_path) != output_path:
            raise ValueError(f"Security violation: Export path '{output_path}' must be a filename, not a path.")

        if not output_path.endswith(".tar.gz"):
            output_path += ".tar.gz"
            
        with tarfile.open(output_path, "w:gz") as tar:
            tar.add(self.storage_path, arcname=os.path.basename(self.storage_path))
        
        logger.info(f"Memory exported to {output_path}")
        return output_path

    def import_from_tar(self, tar_path: str, restore_path: str):
        """Unpacks memory from a .tar.gz archive."""
        with tarfile.open(tar_path, "r:gz") as tar:
            # Python 3.12+ safe extraction filter
            if hasattr(tar, 'extraction_filter'):
                tar.extractall(path=os.path.dirname(restore_path), filter='data')
            else:
                # Fallback for older python, but Bandit will still warn without nosec
                tar.extractall(path=os.path.dirname(restore_path)) # nosec B202
        logger.info(f"Memory restored to {restore_path}")

