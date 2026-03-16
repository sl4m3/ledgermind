"""
Test client-specific model configuration.

Tests verify that each client (claude, gemini, cursor, vscode) can have
its own enrichment model configured and used independently.
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from ledgermind.core.api.memory import Memory
from ledgermind.core.reasoning.enrichment.config import EnrichmentConfig


class TestClientSpecificModels:
    """Test client-specific model storage and retrieval."""
    
    def test_client_specific_model_storage(self, tmp_path):
        """Verify models are stored per-client."""
        memory = Memory(storage_path=str(tmp_path))
        
        # Save client-specific models
        memory.semantic.meta.set_config("enrichment_model_claude", "claude-3.5-sonnet")
        memory.semantic.meta.set_config("enrichment_model_gemini", "gemini-2.5-flash-lite")
        memory.semantic.meta.set_config("enrichment_model_cursor", "claude-3-opus")
        
        # Verify retrieval
        assert memory.semantic.meta.get_config("enrichment_model_claude") == "claude-3.5-sonnet"
        assert memory.semantic.meta.get_config("enrichment_model_gemini") == "gemini-2.5-flash-lite"
        assert memory.semantic.meta.get_config("enrichment_model_cursor") == "claude-3-opus"
    
    def test_enrichment_uses_client_model(self, tmp_path):
        """Verify enrichment config uses correct model for each client."""
        memory = Memory(storage_path=str(tmp_path))
        
        # Save client-specific models
        memory.semantic.meta.set_config("enrichment_model_claude", "claude-3.5-sonnet")
        memory.semantic.meta.set_config("enrichment_model_gemini", "gemini-2.5-flash-lite")
        memory.semantic.meta.set_config("enrichment_provider", "cli")
        
        # Get config for claude client
        claude_config = EnrichmentConfig.from_memory(memory, client="claude")
        assert claude_config.model_name == "claude-3.5-sonnet"
        
        # Get config for gemini client
        gemini_config = EnrichmentConfig.from_memory(memory, client="gemini")
        assert gemini_config.model_name == "gemini-2.5-flash-lite"
        
        # Get config for cursor client (should fallback to default since not set)
        cursor_config = EnrichmentConfig.from_memory(memory, client="cursor")
        assert cursor_config.model_name == "gemini-2.5-flash-lite"  # Default
    
    def test_default_model_fallback(self, tmp_path):
        """Verify fallback to default model when client model not set."""
        memory = Memory(storage_path=str(tmp_path))
        
        # No models configured - should use default
        config = EnrichmentConfig.from_memory(memory, client="unknown_client")
        assert config.model_name == "gemini-2.5-flash-lite"  # Default from config
        
        # No client specified
        config_no_client = EnrichmentConfig.from_memory(memory)
        assert config_no_client.model_name == "gemini-2.5-flash-lite"  # Default
    
    def test_no_model_fallback(self, tmp_path):
        """Verify default model when no models configured."""
        memory = Memory(storage_path=str(tmp_path))
        
        # No models configured
        config = EnrichmentConfig.from_memory(memory, client="claude")
        assert config.model_name == "gemini-2.5-flash-lite"  # Default from dataclass
        
        # No client specified
        config_no_client = EnrichmentConfig.from_memory(memory)
        assert config_no_client.model_name == "gemini-2.5-flash-lite"
    
    def test_mixed_client_models(self, tmp_path):
        """Verify mixed client and global models work correctly."""
        memory = Memory(storage_path=str(tmp_path))
        
        # Save client-specific model for claude only
        memory.semantic.meta.set_config("enrichment_model_claude", "claude-3.5-sonnet")
        memory.semantic.meta.set_config("enrichment_provider", "cli")
        # Note: gemini model not set
        
        # Claude should use client-specific
        claude_config = EnrichmentConfig.from_memory(memory, client="claude")
        assert claude_config.model_name == "claude-3.5-sonnet"
        
        # Gemini should fallback to default (no global enrichment_model anymore)
        gemini_config = EnrichmentConfig.from_memory(memory, client="gemini")
        assert gemini_config.model_name == "gemini-2.5-flash-lite"  # Default
        
        # Unknown client should also fallback to default
        unknown_config = EnrichmentConfig.from_memory(memory, client="unknown")
        assert unknown_config.model_name == "gemini-2.5-flash-lite"  # Default
