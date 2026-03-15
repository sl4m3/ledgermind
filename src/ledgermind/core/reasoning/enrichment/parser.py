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
                # 3. Попытка исправить распространенные проблемы (ТОЛЬКО если json.loads упал)
                try:
                    # Исправление 1: Обратные слэши
                    fixed = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', text)
                    
                    # Исправление 2: Неэкранированные кавычки внутри текста
                    # Ищем " внутри слов или между кириллицей
                    fixed = re.sub(r'(?<=[а-яА-Яa-zA-Z0-9])"(?=[а-яА-Яa-zA-Z0-9\s])', r'\\"', fixed)
                    
                    # Исправление 3: Реальные переносы строк внутри JSON-значений
                    # Ищем текст между кавычками в значениях и заменяем \n на \\n
                    fixed = re.sub(r'":\s*"([^"]*)"', lambda m: '": "' + m.group(1).replace('\n', '\\n') + '"', fixed, flags=re.DOTALL)
                    
                    return json.loads(fixed)
                except Exception:
                    # Последний шанс: убираем все управляющие символы и надеемся на лучшее
                    try:
                        cleaned = re.sub(r'[\x00-\x1F\x7F]', ' ', text)
                        return json.loads(cleaned)
                    except Exception as e3:
                        logger.warning(f"JSON Parse error after all fixes: {e}. Snippet: {text[:200]}...")
                        return None
        except Exception as e:
            logger.error(f"Unexpected parsing error: {e}")
            return None
            
    @staticmethod
    def clean_keywords(raw: Any) -> List[str]:
        if not isinstance(raw, list):
            if isinstance(raw, str): raw = [raw]
            else: return []
            
        keywords = []
        for k in raw:
            if isinstance(k, list):
                # Recursively handle nested lists
                keywords.extend(ResponseParser.clean_keywords(k))
                continue
            
            k_str = str(k)
            if "(" in k_str and ")" in k_str:
                parts = re.split(r'[\(\)]', k_str)
                for p in parts:
                    clean = p.strip()
                    if clean: keywords.append(clean)
            else:
                keywords.append(k_str.strip())
        return list(set([k for k in keywords if k]))
