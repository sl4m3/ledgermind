import re
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("ledgermind-core.enrichment.parser")

class ResponseParser:
    """Extracts and cleans data from LLM responses."""
    
    @staticmethod
    def parse_json(text: str) -> Optional[Dict[str, Any]]:
        if not text: return None
        try:
            # 1. Извлечение JSON блока
            if "```json" in text:
                match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
                if match: text = match.group(1)
            elif "{" in text and "}" in text:
                text = text[text.find("{"):text.rfind("}")+1]
            
            # 2. Очистка от невидимых управляющих символов (кроме легальных в JSON)
            # Удаляем символы в диапазоне 00-1F, которые ломают json.loads
            text = re.sub(r'[\x00-\x1F\x7F]', '', text)
            
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                # 3. Попытка исправить "Invalid \escape" (частая проблема с путями или LaTeX)
                # Заменяем одиночные обратные слэши на двойные, если они не являются частью легальной последовательности
                fixed_text = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', text)
                try:
                    return json.loads(fixed_text)
                except Exception:
                    logger.error(f"JSON Parse error after fix: {e}. Raw snippet: {text[:200]}...")
                    return None
        except Exception as e:
            logger.error(f"Unexpected parsing error: {e}")
            return None
            
    @staticmethod
    def clean_keywords(raw: List[str]) -> List[str]:
        keywords = []
        for k in raw:
            if "(" in k and ")" in k:
                parts = re.split(r'[\(\)]', k)
                for p in parts:
                    clean = p.strip()
                    if clean: keywords.append(clean)
            else:
                keywords.append(k.strip())
        return list(set(keywords))
