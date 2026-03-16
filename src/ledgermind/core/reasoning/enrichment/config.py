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
    def from_memory(cls, memory: Any, mode: str = "rich", enrichment_language: str = "auto", client: str = None) -> 'EnrichmentConfig':
        """Creates config from memory settings.
        
        Args:
            memory: Memory instance
            mode: Enrichment mode (optimal/rich)
            enrichment_language: Language for enrichment
            client: Client identifier (claude/gemini/cursor/vscode) for client-specific models
        """
        config = cls(mode=mode, enrichment_language=enrichment_language)
        if memory and hasattr(memory, 'config'):
            config.max_tokens = getattr(memory.config, 'max_enrichment_tokens', config.max_tokens)

        if memory and hasattr(memory, 'semantic') and hasattr(memory.semantic, 'meta'):
            meta = memory.semantic.meta
            # V7.7+: Use enrichment_* settings
            config.mode = meta.get_config("enrichment_mode") or config.mode
            config.enrichment_language = meta.get_config("enrichment_language") or config.enrichment_language
            
            # V7.9: Only use provider if explicitly set
            provider = meta.get_config("enrichment_provider")
            if provider:
                config.provider = provider
            
            # V7.10: Use client-specific model if available, fallback to global
            if client:
                # Try client-specific model first (e.g., enrichment_model_claude)
                client_model = meta.get_config(f"enrichment_model_{client}")
                if client_model:
                    config.model_name = client_model
                else:
                    # Fallback to global enrichment_model
                    config.model_name = meta.get_config("enrichment_model") or config.model_name
            else:
                # No client specified, use global model
                config.model_name = meta.get_config("enrichment_model") or config.model_name

        return config
