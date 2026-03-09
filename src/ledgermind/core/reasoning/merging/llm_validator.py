import logging
from typing import Dict, Any, Optional
from ..enrichment.clients import CloudLLMClient, LocalLLMClient
from ..enrichment.config import EnrichmentConfig

logger = logging.getLogger("ledgermind.core.merging.llm_validator")

class MergingLLMValidator:
    """
    Validates potential duplicates using LLM when similarity is in the "grey zone".
    """
    def __init__(self, memory: Any):
        self.memory = memory
        # Use maintenance mode for validation to ensure highest quality
        self.config = EnrichmentConfig.from_memory(memory, mode="rich", preferred_language="russian")
        self._client = None

    def _get_client(self):
        if not self._client:
            # Prefer Cloud client for complex reasoning tasks like validation
            try:
                self._client = CloudLLMClient(self.config, self.memory)
            except Exception:
                self._client = LocalLLMClient(self.config, self.memory)
        return self._client

    def validate_duplicate(self, doc1: Dict[str, Any], doc2: Dict[str, Any], score: float) -> bool:
        """
        Asks LLM to confirm if two documents are semantically identical or near-duplicates.
        """
        client = self._get_client()
        
        prompt = f"""
Проверь, являются ли два следующих документа дубликатами или описывают одну и ту же гипотезу/событие.
Система определила сходство как {score:.2f} (серая зона 0.65-0.85).

Документ 1:
Заголовок: {doc1.get('title', 'N/A')}
Теги: {doc1.get('keywords', 'N/A')}
Контент: {doc1.get('content', 'N/A')[:1000]}

Документ 2:
Заголовок: {doc2.get('title', 'N/A')}
Теги: {doc2.get('keywords', 'N/A')}
Контент: {doc2.get('content', 'N/A')[:1000]}

Ответь строго в формате JSON:
{{
  "is_duplicate": true/false,
  "reasoning": "краткое объяснение на русском языке"
}}
"""
        try:
            response = client.call("Ты — эксперт по анализу знаний. Твоя задача — выявлять дубликаты.", prompt)
            if not response:
                return False
            
            import json
            # Extract JSON from potential markdown code blocks
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                is_dup = data.get("is_duplicate", False)
                reason = data.get("reasoning", "No reason provided")
                logger.info(f"LLM Validation Result: {is_dup} | Reason: {reason}")
                return is_dup
            return False
        except Exception as e:
            logger.error(f"LLM Validation Error: {e}")
            return False

import re # For regex search in client response
