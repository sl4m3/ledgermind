import os
import time
import logging
import requests
from typing import Optional, Any

from .config import EnrichmentConfig
from .builder import PromptBuilder

logger = logging.getLogger("ledgermind-core.enrichment.base")


class BaseURLClient:
    """Unified OpenAI-compatible client for enrichment.

    All enrichment goes through a single base URL (config + one endpoint).
    Replaces the legacy terminal clients (Gemini CLI/SDK, AI Studio, OpenRouter,
    local llama-cpp) which were artifacts of the old architecture.
    """

    def __init__(self, config: EnrichmentConfig, memory: Any = None):
        self.config = config
        self.memory = memory
        self._base_url = (config.base_url or "").rstrip("/")
        self._api_key = config.api_key

    def call(self, instructions: str, data: str, fid: str = "unknown") -> Optional[str]:
        """Call the unified endpoint with retry logic.

        Args:
            instructions: System instructions for the task.
            data: The data to process (logs, rationales, etc.).
            fid: File ID for logging.

        Returns:
            Response text or None on failure.
        """
        if not self._base_url:
            logger.error(f"BaseURL: endpoint not configured for {fid}")
            return None

        try:
            full_prompt = PromptBuilder.wrap_with_data(instructions, data, self.config)

            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            url = f"{self._base_url}/chat/completions"
            body = {
                "model": self.config.model_name,
                "messages": [
                    {"role": "system", "content": "You are a technical expert analyzing software development logs and decisions. Return structured JSON responses."},
                    {"role": "user", "content": full_prompt},
                ],
                "max_tokens": min(self.config.max_tokens, 8192),
                "temperature": 0.1,
            }

            if self.config.json_mode:
                body["response_format"] = {"type": "json_object"}

            logger.info(f"BaseURL: Calling {self.config.model_name} @ {self._base_url} for {fid}...")

            for attempt in range(1, self.config.retry_attempts + 1):
                logger.info(f"Attempt {attempt}/{self.config.retry_attempts}: BaseURL call...")
                try:
                    response = requests.post(
                        url, headers=headers, json=body, timeout=self.config.timeout
                    )
                    if response.status_code == 200:
                        result = response.json()
                        content = (
                            result.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
                        if content:
                            logger.info(f"BaseURL: Success for {fid}")
                            return content.strip()
                        logger.error(f"BaseURL: Empty response for {fid}")
                    else:
                        logger.error(f"BaseURL: HTTP {response.status_code} - {response.text[:200]}")
                except requests.exceptions.Timeout:
                    logger.error(f"BaseURL: Timeout on attempt {attempt}")
                except requests.exceptions.RequestException as e:
                    logger.error(f"BaseURL: Request error: {e}")
                except Exception as e:
                    logger.error(f"BaseURL: Parse error: {e}")

                if attempt < self.config.retry_attempts:
                    delay = self.config.retry_delay * attempt
                    logger.info(f"Retrying in {delay}s...")
                    time.sleep(delay)

            return None
        except Exception as e:
            logger.error(f"BaseURL: Unexpected error: {e}")
            return None

    def is_available(self) -> bool:
        """Check if the endpoint is configured."""
        return bool(self._base_url)
