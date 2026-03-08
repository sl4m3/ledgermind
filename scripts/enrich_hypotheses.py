import os
import sys
import logging
import re

# Настройка логирования
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

sys.path.insert(0, os.path.abspath("src"))
from ledgermind.core.api.memory import Memory
from ledgermind.core.reasoning.llm_enrichment import LLMEnricher

storage_path = os.path.abspath("../.ledgermind")

def main():
    print(f"Storage path: {storage_path}")
    print(">>> Starting Hypothesis Enrichment & HARD Language Audit...", flush=True)

    if not os.path.exists(storage_path):
        print(f"   [ERROR] Storage path does not exist: {storage_path}")
        sys.exit(1)

    # 1. Инициализация памяти
    print("1. Initializing Memory connection...", flush=True)
    memory = Memory(storage_path=storage_path, vector_workers=0)

    # 2. Определение целевого языка
    preferred_lang = memory.semantic.meta.get_config("preferred_language", "auto")
    print(f"2. Target language detected: {preferred_lang}", flush=True)

    # 3. Инициализация обогатителя
    enricher = LLMEnricher(
        mode="rich", 
        preferred_language=preferred_lang
    )

    # 4. Жесткий Языковой аудит
    if preferred_lang == "russian":
        print(f"3. Running HARD Language Audit (Russian density)...", flush=True)
        all_metas = memory.semantic.meta.list_all()
        to_repair = []
        
        from ledgermind.core.stores.semantic_store.loader import MemoryLoader
        
        for m in all_metas:
            fid = m['fid']
            file_path = os.path.join(memory.semantic.repo_path, fid)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    data, _ = MemoryLoader.parse(content)
                    
                    # Check rationale content for Cyrillic
                    text_to_check = (data.get('context', {}).get('rationale', '') or data.get('rationale', '') or "").lower()
                    
                    # HARD CHECK: If no cyrillic at all in a non-empty rationale
                    if text_to_check.strip():
                        has_cyrillic = bool(re.search(r'[а-яё]', text_to_check))
                        if not has_cyrillic:
                            to_repair.append(fid)
            except Exception as e:
                print(f"   [WARN] Could not parse {fid}: {e}")
                continue

        if to_repair:
            print(f"   - Found {len(to_repair)} English-only records. Resetting to pending...", flush=True)
            with memory.semantic.transaction():
                for fid in to_repair:
                    memory.semantic.update_decision(fid, {"enrichment_status": "pending"}, "Audit: Pure English detected. Queued for translation.")
        else:
            print("   - All records contain Russian text.", flush=True)

    # 5. Запуск процесса обогащения через LLM
    print("4. Starting Enrichment Batch...", flush=True)
    try:
        from ledgermind.core.core.schemas import DecisionStream
        from ledgermind.core.stores.semantic_store.loader import MemoryLoader
        
        # Get pending proposals from meta index
        pending_metas = memory.semantic.meta.get_by_status("pending")
        if not pending_metas:
            # Fallback check for enrichment_status
            pending_metas = [m for m in memory.semantic.meta.list_all() if m.get('enrichment_status') == 'pending']
            
        proposals_to_process = []
        for m in pending_metas:
            fid = m['fid']
            file_path = os.path.join(memory.semantic.repo_path, fid)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data, _ = MemoryLoader.parse(f.read())
                    obj = DecisionStream(**data.get('context', {}))
                    obj.fid = fid # Critical for saving back
                    proposals_to_process.append(obj)
            except Exception as e:
                print(f"   [WARN] Failed to load {fid} for enrichment: {e}")

        if not proposals_to_process:
            print("   - Info: No pending work found.", flush=True)
        else:
            print(f"   - Processing {len(proposals_to_process)} proposals...", flush=True)
            results = enricher.process_batch(proposals_to_process, memory.episodic, memory=memory)
            print(f"   - Done: Successfully processed {len(results)} proposals.", flush=True)
            
    except Exception as e:
        print(f"   [ERROR] Enrichment process failed: {e}", flush=True)
    finally:
        memory.close()
        print("\n>>> session complete!", flush=True)

if __name__ == "__main__":
    main()
