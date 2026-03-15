import os
import time
import logging
import requests
from typing import Optional, Any
from .config import EnrichmentConfig
from .builder import PromptBuilder

logger = logging.getLogger("ledgermind-core.enrichment.openrouter")

class OpenRouterClient:
    """
    Strategy for OpenRouter API (Cloud).
    Supports 100+ LLM providers through unified API.
    """
    
    # OpenRouter endpoint
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    
    def __init__(self, config: EnrichmentConfig, memory: Any = None):
        self.config = config
        self.memory = memory
        self._api_key = None
        
        # Load API key from memory config or environment
        if memory and hasattr(memory, 'semantic') and hasattr(memory.semantic, 'meta'):
            meta = memory.semantic.meta
            self._api_key = meta.get_config("openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY")
        else:
            self._api_key = os.environ.get("OPENROUTER_API_KEY")

    def call(self, instructions: str, data: str, fid: str = "unknown") -> Optional[str]:
        """
        Call OpenRouter API with retry logic.
        
        Args:
            instructions: System instructions for the task
            data: The data to process (logs, rationales, etc.)
            fid: File ID for logging
            
        Returns:
            Response text or None on failure
        """
        if not self._api_key:
            logger.error(f"OpenRouter: API key not set for {fid}")
            return None
        
        try:
            full_prompt = PromptBuilder.wrap_with_data(instructions, data, self.config)
            
            # Build request headers
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                # Optional headers for OpenRouter ranking
                "HTTP-Referer": os.environ.get("OR_SITE_URL", "https://github.com/sl4m3/ledgermind"),
                "X-Title": os.environ.get("OR_SITE_NAME", "LedgerMind"),
            }
            
            # Build request body
            body = {
                "model": self.config.model_name,
                "messages": [
                    {"role": "system", "content": "You are a technical expert analyzing software development logs and decisions. Return structured JSON responses."},
                    {"role": "user", "content": full_prompt}
                ],
                "max_tokens": min(self.config.max_tokens, 4096),  # Cap at model limit
                "temperature": 0.1,  # Low temperature for consistent technical output
            }
            
            # Add optional parameters
            # (provider ordering can be added here if needed)
            
            logger.info(f"OpenRouter: Calling {self.config.model_name} for {fid}...")
            
            for attempt in range(1, self.config.retry_attempts + 1):
                logger.info(f"Attempt {attempt}/{self.config.retry_attempts}: OpenRouter API call...")
                
                try:
                    response = requests.post(
                        self.API_URL,
                        headers=headers,
                        json=body,
                        timeout=self.config.timeout
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        if content:
                            logger.info(f"OpenRouter: Success for {fid}")
                            return content.strip()
                        else:
                            logger.error(f"OpenRouter: Empty response for {fid}")
                    else:
                        logger.error(f"OpenRouter: HTTP {response.status_code} - {response.text[:200]}")
                        
                except requests.exceptions.Timeout:
                    logger.error(f"OpenRouter: Timeout on attempt {attempt}")
                except requests.exceptions.RequestException as e:
                    logger.error(f"OpenRouter: Request error: {e}")
                except Exception as e:
                    logger.error(f"OpenRouter: Parse error: {e}")
                
                if attempt < self.config.retry_attempts:
                    delay = self.config.retry_delay * attempt
                    logger.info(f"Retrying in {delay}s...")
                    time.sleep(delay)
            
            return None
            
        except Exception as e:
            logger.error(f"OpenRouter: Unexpected error: {e}")
            return None

    def is_available(self) -> bool:
        """Check if OpenRouter client is properly configured."""
        return bool(self._api_key)

    def get_model_info(self) -> dict:
        """Get current model configuration."""
        return {
            "provider": "openrouter",
            "model": self.config.model_name,
            "api_key_configured": bool(self._api_key),
        }
