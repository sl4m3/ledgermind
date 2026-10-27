"""Installer provider profiles and install-time probes."""

from .embedding_api import OpenAICompatibleEmbeddingProvider
from .generation import build_generation_profiles
from .probes import probe_embedding_api, probe_generation

__all__ = [
    "OpenAICompatibleEmbeddingProvider",
    "build_generation_profiles",
    "probe_embedding_api",
    "probe_generation",
]
