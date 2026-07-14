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
    json_mode: bool = True                  # Use response_format=json_object (OpenAI/OpenRouter only, not NVIDIA NIM)
    enrichment_language: str = "english"

    @classmethod
    def from_memory(cls, memory: Any, enrichment_language: str = "english") -> 'EnrichmentConfig':
        """Creates config from memory settings.

        Source priority (highest first):
        1. LedgermindConfig (memory.config) — enrichment_base_url / enrichment_model / enrichment_api_key
        2. ~/.ledgermind/hermes/config.json (language, enrichment.provider, enrichment.model, enrichment.base_url)
        3. ~/.hermes/plugins/ledgermind/.env (LEDGERMIND_API_KEY)
        4. installers.ENRICHMENT_DEFAULTS for the configured provider
        """
        config = cls(enrichment_language=enrichment_language)

        # 1. From LedgermindConfig
        if memory and hasattr(memory, 'config'):
            cfg = memory.config
            config.provider = getattr(cfg, 'enrichment_provider', config.provider) or config.provider
            config.base_url = getattr(cfg, 'enrichment_base_url', None) or config.base_url
            config.api_key = getattr(cfg, 'enrichment_api_key', None) or config.api_key
            config.model_name = getattr(cfg, 'enrichment_model', None) or config.model_name

        # 2. From ledgermind hermes config (~/.ledgermind/hermes/config.json)
        hermes_config_path = Path.home() / ".ledgermind" / "hermes" / "config.json"
        if hermes_config_path.exists():
            try:
                hc = json.loads(hermes_config_path.read_text())
                config.enrichment_language = config.enrichment_language or hc.get("language", "english")
                enrich = hc.get("enrichment", {})
                config.base_url = config.base_url or enrich.get("base_url")
                config.model_name = config.model_name or enrich.get("model")
                config.provider = config.provider or enrich.get("provider", config.provider)
            except Exception:
                pass

        # 3. From agent config.json (storage_path/config.json)
        from ledgermind.core.stores.semantic_store.meta import load_config
        storage_path = getattr(memory, 'storage_path', None) if memory else None
        hc = load_config(storage_path)
        hc_lang = hc.get("language")
        if hc_lang:
            config.enrichment_language = hc_lang
        enrich = hc.get("enrichment", {})
        hc_url = enrich.get("base_url")
        if hc_url:
            config.base_url = hc_url
        hc_model = enrich.get("model")
        if hc_model:
            config.model_name = hc_model
        hc_provider = enrich.get("provider")
        if hc_provider:
            config.provider = hc_provider

        # json_mode is always enabled — all providers support response_format: json_object
        hc_key = enrich.get("api_key")
        if hc_key:
            config.api_key = hc_key

        # 4. API key from storage_path/.env
        if not config.api_key:
            from ledgermind.core.stores.semantic_store.meta import _get_storage_dir
            env_dir = Path(storage_path) if storage_path else _get_storage_dir()
            env_path = env_dir / ".env"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("LEDGERMIND_API_KEY="):
                        config.api_key = line.split("=", 1)[1].strip()
                        break

        # 4. Fallback to ENRICHMENT_DEFAULTS for the provider
        defaults = ENRICHMENT_DEFAULTS.get(config.provider, ENRICHMENT_DEFAULTS["openrouter"])
        config.base_url = config.base_url or defaults["base_url"]
        config.model_name = config.model_name or defaults["model"]

        return config
