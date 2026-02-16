import os
import tarfile
import logging
import shutil
from typing import Optional
from datetime import datetime

logger = logging.getLogger("agent-memory-core.transfer")

class MemoryTransferManager:
    """Handles Export/Import and S3 backups of the memory system."""
    
    def __init__(self, storage_path: str):
        self.storage_path = storage_path

    def export_to_tar(self, output_path: str) -> str:
        """Packs the entire memory storage into a .tar.gz archive."""
        if not output_path.endswith(".tar.gz"):
            output_path += ".tar.gz"
            
        with tarfile.open(output_path, "w:gz") as tar:
            tar.add(self.storage_path, arcname=os.path.basename(self.storage_path))
        
        logger.info(f"Memory exported to {output_path}")
        return output_path

    def import_from_tar(self, tar_path: str, restore_path: str):
        """Unpacks memory from a .tar.gz archive."""
        with tarfile.open(tar_path, "r:gz") as tar:
            tar.extractall(path=os.path.dirname(restore_path))
        logger.info(f"Memory restored to {restore_path}")

    def backup_to_s3(self, bucket: str, key_prefix: str = "backups/"):
        """Exports and uploads memory to an S3 bucket."""
        try:
            import boto3
            s3 = boto3.client('s3')
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            temp_file = f"memory_backup_{timestamp}.tar.gz"
            
            self.export_to_tar(temp_file)
            
            s3_key = f"{key_prefix}{temp_file}"
            s3.upload_file(temp_file, bucket, s3_key)
            
            os.remove(temp_file)
            logger.info(f"Backup successfully uploaded to s3://{bucket}/{s3_key}")
            return s3_key
        except ImportError:
            logger.error("boto3 not installed. S3 backup failed.")
            raise
        except Exception as e:
            logger.error(f"S3 backup failed: {e}")
            raise
