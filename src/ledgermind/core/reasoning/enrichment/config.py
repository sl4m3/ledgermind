from dataclasses import dataclass
from typing import Any

@dataclass
class EnrichmentConfig:
    """Settings for the enrichment process."""
    mode: str = "rich"  # "optimal" (local) or "rich" (cloud)
    provider: str = "cli"  # "cli" or "openrouter"
    max_tokens: int = 100000
    retry_attempts: int = 3
    retry_delay: int = 5
    timeout: int = 300
    enrichment_language: str = "auto"  # V7.8: Renamed from preferred_language
    model_name: str = "gemini-2.5-flash-lite"

    @classmethod
    def from_memory(cls, memory: Any, mode: str = "rich", enrichment_language: str = "auto") -> 'EnrichmentConfig':
        """Creates config from memory settings."""
        config = cls(mode=mode, enrichment_language=enrichment_language)
        if memory and hasattr(memory, 'config'):
            config.max_tokens = getattr(memory.config, 'max_enrichment_tokens', config.max_tokens)

        if memory and hasattr(memory, 'semantic') and hasattr(memory.semantic, 'meta'):
            meta = memory.semantic.meta
            # V7.7+: Use enrichment_* settings
            config.mode = meta.get_config("enrichment_mode") or config.mode
            config.model_name = meta.get_config("enrichment_model") or config.model_name
            config.enrichment_language = meta.get_config("enrichment_language") or config.enrichment_language
            # V7.9: Only use provider if explicitly set
            provider = meta.get_config("enrichment_provider")
            if provider:
                config.provider = provider

        return config
