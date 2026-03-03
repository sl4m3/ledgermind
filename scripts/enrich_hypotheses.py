import os
import sys
import logging

# Настройка логирования для отслеживания внутренних сообщений
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Добавление src в путь для импорта модулей ledgermind
sys.path.insert(0, os.path.abspath("src"))
from ledgermind.core.api.memory import Memory
from ledgermind.core.reasoning.llm_enrichment import LLMEnricher

# Путь к хранилищу (на один уровень выше директории проекта)
storage_path = os.path.abspath("../.ledgermind")

def main():
    print(f"Storage path: {storage_path}")
    print(">>> Starting Hypothesis Enrichment Script (Step 5 only)...", flush=True)

    if not os.path.exists(storage_path):
        print(f"   [ERROR] Storage path does not exist: {storage_path}")
        sys.exit(1)

    # 1. Инициализация памяти без сброса вотермарков
    print("1. Initializing Memory connection...", flush=True)
    # Используем vector_workers=0 для экономии памяти в Termux
    memory = Memory(storage_path=storage_path, vector_workers=0)

    # 2. Запуск процесса обогащения через LLM
    print("2. Starting Enrichment Batch (LLM Synthesis)...", flush=True)
    try:
        # Использование конфигурации "rich" и модели gemini-2.5-flash-lite
        enricher = LLMEnricher(
            mode="rich", 
            client_name="gemini", 
            model_name="gemini-2.5-flash-lite"
        )
        
        # Обработка всех ожидающих предложений (proposals)
        results = enricher.process_batch(memory)

        if not results:
            print("   - Info: No pending proposals found or all already enriched.", flush=True)
        else:
            print(f"   - Done: Successfully enriched {len(results)} proposals.", flush=True)
            
    except Exception as e:
        print(f"   [ERROR] Enrichment process failed: {e}", flush=True)
        import traceback
        traceback.print_exc()
    finally:
        # Обязательное закрытие соединений
        memory.close()
        print("\n>>> Enrichment session complete!", flush=True)

if __name__ == "__main__":
    main()
