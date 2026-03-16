import os
import time
import logging
import requests
from typing import Optional, Any
from .config import EnrichmentConfig
from .builder import PromptBuilder

logger = logging.getLogger("ledgermind-core.enrichment.aistudio")

class AIStudioClient:
    """
    Strategy for Google AI Studio API (Cloud).
    Supports Gemini models through Google AI Studio.
    """
    
    # AI Studio endpoint
    API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    
    def __init__(self, config: EnrichmentConfig, memory: Any = None):
        self.config = config
        self.memory = memory
        self._api_key = None
        
        # Load API key from memory config or environment
        if memory and hasattr(memory, 'semantic') and hasattr(memory.semantic, 'meta'):
            meta = memory.semantic.meta
            self._api_key = meta.get_config("aistudio_api_key") or os.environ.get("GOOGLE_API_KEY")
        else:
            self._api_key = os.environ.get("GOOGLE_API_KEY")
    
    def call(self, instructions: str, data: str, fid: str = "unknown") -> Optional[str]:
        """
        Call AI Studio API with retry logic.
        
        Args:
            instructions: System instructions for the task
            data: The data to process (logs, rationales, etc.)
            fid: File ID for logging
            
        Returns:
            Response text or None on failure
        """
        if not self._api_key:
            logger.error(f"AI Studio: API key not set for {fid}")
            return None
        
        try:
            full_prompt = PromptBuilder.wrap_with_data(instructions, data, self.config)
            
            # Build API URL with model name
            model_name = self.config.model_name or "gemini-1.5-pro"
            api_url = self.API_URL.format(model=model_name)
            
            # Build request parameters
            params = {
                "key": self._api_key,
            }
            
            # Build request body
            body = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": full_prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.1,  # Low temperature for consistent technical output
                    "maxOutputTokens": min(self.config.max_tokens, 8192),  # Cap at model limit
                }
            }
            
            logger.info(f"AI Studio: Calling {model_name} for {fid}...")
            
            for attempt in range(1, self.config.retry_attempts + 1):
                logger.info(f"Attempt {attempt}/{self.config.retry_attempts}: AI Studio API call...")
                
                try:
                    response = requests.post(
                        api_url,
                        params=params,
                        json=body,
                        timeout=self.config.timeout
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        # AI Studio response format
                        candidates = result.get("candidates", [])
                        if candidates and len(candidates) > 0:
                            content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            if content:
                                logger.info(f"AI Studio: Success for {fid}")
                                return content.strip()
                        
                        logger.error(f"AI Studio: Empty response for {fid}")
                    else:
                        logger.error(f"AI Studio: HTTP {response.status_code} - {response.text[:200]}")
                        
                except requests.exceptions.Timeout:
                    logger.error(f"AI Studio: Timeout on attempt {attempt}")
                except requests.exceptions.RequestException as e:
                    logger.error(f"AI Studio: Request error: {e}")
                except Exception as e:
                    logger.error(f"AI Studio: Parse error: {e}")
                
                if attempt < self.config.retry_attempts:
                    delay = self.config.retry_delay * attempt
                    logger.info(f"Retrying in {delay}s...")
                    time.sleep(delay)
            
            return None
            
        except Exception as e:
            logger.error(f"AI Studio: Unexpected error: {e}")
            return None
    
    def is_available(self) -> bool:
        """Check if AI Studio client is properly configured."""
        return bool(self._api_key)
    
    def get_model_info(self) -> dict:
        """Get current model configuration."""
        return {
            "provider": "aistudio",
            "model": self.config.model_name or "gemini-1.5-pro",
            "api_key_configured": bool(self._api_key),
        }
