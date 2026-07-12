from dataclasses import dataclass, field
from typing import Any, Optional
import os
import json
from pathlib import Path


# Mirrors installers.ENRICHMENT_DEFAULTS — used only if nothing is configured.
ENRICHMENT_DEFAULTS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "deepseek-ai/deepseek-v4-flash",
    },
    "aistudio": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemma-4-31b-it",
    },
    "custom": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama-3-8b",
    },
}


@dataclass
class EnrichmentConfig:
    """Settings for the enrichment process.

    Unified pipeline: a single OpenAI-compatible endpoint (base_url) is used
    for all enrichment. No provider/client branching — everything goes through
    config + one base URL (legacy terminal clients removed).
    """
    provider: str = "openrouter"
    base_url: Optional[str] = None          # OpenAI-compatible /v1/chat/completions endpoint
    api_key: Optional[str] = None           # Bearer token for the endpoint
    model_name: str = "nvidia/nemotron-3-super-120b-a12b:free"
    max_tokens: int = 100000
    retry_attempts: int = 3
    retry_delay: int = 5
    timeout: int = 300
    enrichment_language: str = "auto"       # V7.8: Renamed from preferred_language

    @classmethod
    def from_memory(cls, memory: Any, enrichment_language: str = "auto") -> 'EnrichmentConfig':
        """Creates config from memory settings.

        Source priority (highest first):
        1. LedgermindConfig (memory.config) — enrichment_base_url / enrichment_model / enrichment_api_key
        2. Hermes plugin config: ~/.hermes/plugins/ledgermind/config.json (base_url, model)
           + ~/.hermes/plugins/ledgermind/.env (LEDGERMIND_API_KEY)
        3. installers.ENRICHMENT_DEFAULTS for the configured provider
        """
        config = cls(enrichment_language=enrichment_language)

        # 1. From LedgermindConfig
        if memory and hasattr(memory, 'config'):
            cfg = memory.config
            config.provider = getattr(cfg, 'enrichment_provider', config.provider) or config.provider
            config.base_url = getattr(cfg, 'enrichment_base_url', None) or config.base_url
            config.api_key = getattr(cfg, 'enrichment_api_key', None) or config.api_key
            config.model_name = getattr(cfg, 'enrichment_model', None) or config.model_name

        # 2. From Hermes plugin config (what installers.py writes)
        plugin_dir = Path.home() / ".hermes" / "plugins" / "ledgermind"
        plugin_config_path = plugin_dir / "config.json"
        if plugin_config_path.exists():
            try:
                pc = json.loads(plugin_config_path.read_text())
                config.base_url = config.base_url or pc.get("base_url")
                config.model_name = config.model_name or pc.get("model")
                config.provider = config.provider or pc.get("provider", config.provider)
            except Exception:
                pass
            # API key from .env
            env_path = plugin_dir / ".env"
            if env_path.exists() and not config.api_key:
                for line in env_path.read_text().splitlines():
                    if line.startswith("LEDGERMIND_API_KEY="):
                        config.api_key = line.split("=", 1)[1].strip()
                        break

        # 3. From meta store (legacy enrichment_* keys, lowest priority)
        if memory and hasattr(memory, 'semantic') and hasattr(memory.semantic, 'meta'):
            meta = memory.semantic.meta
            config.enrichment_language = meta.get_config("enrichment_language") or config.enrichment_language
            config.base_url = config.base_url or meta.get_config("enrichment_base_url")
            config.api_key = config.api_key or meta.get_config("enrichment_api_key")
            config.model_name = config.model_name or meta.get_config("enrichment_model")

        # 4. Fallback to ENRICHMENT_DEFAULTS for the provider
        defaults = ENRICHMENT_DEFAULTS.get(config.provider, ENRICHMENT_DEFAULTS["openrouter"])
        config.base_url = config.base_url or defaults["base_url"]
        config.model_name = config.model_name or defaults["model"]

        return config
