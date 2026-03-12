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
                    # 4. Попытка исправить неэкранированные кавычки внутри строк
                    # Это происходит, когда LLM генерирует "text "quoted" more" вместо "text \"quoted\" more"
                    try:
                        # Простая эвристика: заменяем " внутри строк на \"
                        # Ищем паттерны вроде: "key": "value "nested" continue"
                        fixed_text2 = re.sub(r'"(?=[^",\[\]{}]*\s+\w+)', r'\\"', text)
                        return json.loads(fixed_text2)
                    except Exception as e2:
                        # V7.7: Additional fix - remove markdown formatting inside JSON strings
                        try:
                            # Remove **bold** and *italic* markers that break JSON
                            cleaned = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
                            cleaned = re.sub(r'\*([^*]+)\*', r'\1', cleaned)
                            cleaned = re.sub(r'__([^_]+)__', r'\1', cleaned)
                            cleaned = re.sub(r'_([^_]+)_', r'\1', cleaned)
                            # Remove newlines within strings (replace \n with space)
                            cleaned = re.sub(r'(?<!\\)\\n', ' ', cleaned)
                            return json.loads(cleaned)
                        except Exception as e3:
                            logger.warning(f"JSON Parse error after all fixes: {e}. Snippet: {text[:500]}...")
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
