
import os
import json
import uuid
import logging
from datetime import datetime
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import DecisionPhase, DecisionVitality

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrator")

def migrate_v2_9_0():
    storage_path = os.environ.get("LEDGERMIND_STORAGE", "./memory")
    if not os.path.exists(storage_path):
        logger.error(f"Storage path {storage_path} not found.")
        return

    memory = Memory(storage_path=storage_path)
    try:
        metas = memory.semantic.meta.list_all()
        updated_count = 0
        
        with memory.semantic.transaction():
            for m in metas:
                fid = m['fid']
                ctx_json = m.get('context_json', '{}')
                try:
                    ctx = json.loads(ctx_json)
                except:
                    continue
                
                needs_update = False
                
                # 1. Add missing decision_id
                if "decision_id" not in ctx and m.get('kind') in ('decision', 'proposal'):
                    ctx['decision_id'] = str(uuid.uuid4())
                    needs_update = True
                
                # 2. Add missing phase/vitality for potential streams
                if "phase" not in ctx:
                    # Heuristic: active decisions become EMERGENT, others PATTERN
                    if m.get('status') == 'active' and m.get('kind') == 'decision':
                        ctx['phase'] = DecisionPhase.EMERGENT.value
                    else:
                        ctx['phase'] = DecisionPhase.PATTERN.value
                    needs_update = True
                
                if "vitality" not in ctx:
                    ctx['vitality'] = DecisionVitality.ACTIVE.value
                    needs_update = True
                
                if needs_update:
                    logger.info(f"Migrating {fid}...")
                    memory.semantic.update_decision(fid, ctx, "Migration: v2.9.0 Lifecycle fields backfill")
                    updated_count += 1
                    
        logger.info(f"Migration complete. Updated {updated_count} records.")
    finally:
        memory.close()

if __name__ == "__main__":
    migrate_v2_9_0()
