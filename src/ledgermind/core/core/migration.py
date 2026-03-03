import os
import yaml
import logging
from typing import Dict, Any, List
from ledgermind.core.stores.semantic_store.loader import MemoryLoader

logger = logging.getLogger("ledgermind-core.migration")

class MigrationEngine:
    """
    Handles data format evolution and ensures backward compatibility
    between different versions of the memory system.
    """
    
    def __init__(self, semantic_store):
        self.semantic = semantic_store

    def run_all(self):
        """Executes all necessary migrations for the current version."""
        # Ensure we have exclusive access during migration
        if hasattr(self.semantic, "_fs_lock"):
            self.semantic._fs_lock.acquire(exclusive=True)
        try:
            logger.info("Checking memory format compatibility...")
            self.migrate_to_v1_22()
            # After all file-level migrations, rebuild the metadata index
            # to ensure hit_count, namespace and other SQLite-only fields are fresh
            self.semantic.sync_meta_index()
        finally:
            if hasattr(self.semantic, "_fs_lock"):
                self.semantic._fs_lock.release()

    def migrate_to_v1_22(self):
        """
        Migration to v1.22.0 standards:
        - Ensures 'target' length >= 3
        - Ensures 'kind' exists
        - Ensures 'namespace' exists
        - Fixes 'rationale' if too short
        """
        all_files = []
        for root, _, filenames in os.walk(self.semantic.repo_path):
            if ".git" in root or ".tx_backup" in root: continue
            for f in filenames:
                if f.endswith(".md"):
                    rel_path = os.path.relpath(os.path.join(root, f), self.semantic.repo_path)
                    all_files.append(rel_path)

        modified_count = 0
        
        for f in all_files:
            file_path = os.path.join(self.semantic.repo_path, f)
            try:
                with open(file_path, 'r', encoding='utf-8') as stream:
                    content = stream.read()
                
                data, body = MemoryLoader.parse(content)
                if not data: continue
                
                changed = False
                ctx = data.get("context", {})
                
                # 1. Fix Kind
                if "kind" not in data:
                    data["kind"] = "decision"
                    changed = True
                
                # 2. Fix Target Length
                target = ctx.get("target", "unknown")
                if len(target) < 3:
                    ctx["target"] = f"migrated_{target}"
                    changed = True
                
                # 3. Fix Rationale Length
                rationale = ctx.get("rationale", "")
                if len(rationale) < 10:
                    ctx["rationale"] = f"{rationale} (Migrated content)"
                    changed = True
                
                # 4. Fix Namespace
                if "namespace" not in ctx:
                    ctx["namespace"] = "default"
                    changed = True
                
                if changed:
                    data["context"] = ctx
                    new_content = MemoryLoader.stringify(data, body)
                    with open(file_path, 'w', encoding='utf-8') as stream:
                        stream.write(new_content)
                    
                    # Update metadata index immediately
                    ts = data.get("timestamp")
                    from datetime import datetime
                    if isinstance(ts, str): ts = datetime.fromisoformat(ts)
                    
                    self.semantic.meta.upsert(
                        fid=f,
                        target=ctx["target"],
                        title=ctx.get("title", ""),
                        status=ctx.get("status", "active"),
                        kind=data["kind"],
                        timestamp=ts or datetime.now(),
                        namespace=ctx["namespace"],
                        superseded_by=ctx.get("superseded_by")
                    )

                    
                    # Add to git staging
                    if hasattr(self.semantic.audit, "run"):
                        self.semantic.audit.run(["add", "--", f])
                    
                    modified_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to migrate {f}: {e}")

        if modified_count > 0:
            logger.info(f"Migration completed: {modified_count} files normalized to v1.22.0")
            if hasattr(self.semantic.audit, "run"):
                self.semantic.audit.commit_transaction(f"System Migration: Normalized {modified_count} files to v1.22.0")
        else:
            logger.debug("Memory format is already up to date.")
