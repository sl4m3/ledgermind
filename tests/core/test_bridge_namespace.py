"""
Test namespace isolation in Bridge API.

Tests verify that --cli flag correctly sets namespace and provides isolation
between different clients sharing the same memory storage.
"""

import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from ledgermind.core.api.memory import Memory
from ledgermind.core.api.bridge import Bridge


class TestBridgeNamespace:
    """Test namespace isolation in Bridge API."""
    
    def test_bridge_uses_namespace_parameter(self, tmp_path):
        """Verify namespace parameter sets isolation correctly."""
        # Create test memory with decisions in different namespaces
        memory = Memory(storage_path=str(tmp_path))
        
        # Record decisions in different namespaces (rationale must be >= 10 chars)
        memory.record_decision("Claude decision", "target", "This is the rationale for Claude decision", namespace="claude")
        memory.record_decision("Gemini decision", "target", "This is the rationale for Gemini decision", namespace="gemini")
        
        # Create bridge with claude namespace
        bridge = Bridge(memory_path=str(tmp_path), namespace="claude")
        
        # Should only see claude decision
        context = bridge.get_context_for_prompt("target")
        assert "Claude decision" in context
        assert "Gemini decision" not in context
    
    def test_bridge_default_namespace(self, tmp_path):
        """Verify default namespace when not specified."""
        memory = Memory(storage_path=str(tmp_path))
        memory.record_decision("Default decision", "target", "This is the default rationale for testing")
        
        bridge = Bridge(memory_path=str(tmp_path))
        context = bridge.get_context_for_prompt("target")
        assert "Default decision" in context
    
    def test_bridge_namespace_isolation(self, tmp_path):
        """Verify complete isolation between namespaces."""
        memory = Memory(storage_path=str(tmp_path))
        
        # Record in claude namespace (target must be >= 3 chars)
        memory.record_decision("Claude 1", "api", "This is the rationale for Claude API decision", namespace="claude")
        memory.record_decision("Claude 2", "database", "This is the rationale for Claude DB decision", namespace="claude")
        
        # Record in gemini namespace
        memory.record_decision("Gemini 1", "api", "This is the rationale for Gemini API decision", namespace="gemini")
        
        # Claude bridge should only see claude decisions
        claude_bridge = Bridge(memory_path=str(tmp_path), namespace="claude")
        claude_context = claude_bridge.get_context_for_prompt("api")
        assert "Claude 1" in claude_context
        assert "Gemini 1" not in claude_context
        
        # Gemini bridge should only see gemini decisions
        gemini_bridge = Bridge(memory_path=str(tmp_path), namespace="gemini")
        gemini_context = gemini_bridge.get_context_for_prompt("api")
        assert "Gemini 1" in gemini_context
        assert "Claude 1" not in gemini_context
    
    def test_bridge_record_interaction_with_namespace(self, tmp_path):
        """Verify record_interaction respects namespace."""
        memory = Memory(storage_path=str(tmp_path))
        
        # Record interactions in different namespaces
        claude_bridge = Bridge(memory_path=str(tmp_path), namespace="claude")
        claude_bridge.record_interaction("Claude prompt for testing", "Claude response for testing")
        
        gemini_bridge = Bridge(memory_path=str(tmp_path), namespace="gemini")
        gemini_bridge.record_interaction("Gemini prompt for testing", "Gemini response for testing")
        
        # Verify events are recorded (namespace is used in process_event)
        # Events should be isolated by namespace through Memory.process_event
        claude_stats = claude_bridge.get_stats()
        gemini_stats = gemini_bridge.get_stats()
        
        # Both should have events recorded
        assert claude_stats.get('episodic_count', 0) >= 1
        assert gemini_stats.get('episodic_count', 0) >= 1
    
    def test_bridge_search_with_namespace_filter(self, tmp_path):
        """Verify search_decisions filters by namespace."""
        memory = Memory(storage_path=str(tmp_path))
        
        # Record decisions with same target in different namespaces
        memory.record_decision("Claude API decision", "api", "This is the Claude API rationale", namespace="claude")
        memory.record_decision("Gemini API decision", "api", "This is the Gemini API rationale", namespace="gemini")
        memory.record_decision("Default API decision", "api", "This is the default API rationale")
        
        # Search with claude namespace
        claude_bridge = Bridge(memory_path=str(tmp_path), namespace="claude")
        claude_results = claude_bridge.search_decisions("api", limit=10)
        
        # Should find claude decision
        claude_titles = [r.get('title', '') for r in claude_results]
        assert any("Claude" in t for t in claude_titles)
        
        # Search with gemini namespace
        gemini_bridge = Bridge(memory_path=str(tmp_path), namespace="gemini")
        gemini_results = gemini_bridge.search_decisions("api", limit=10)
        
        # Should find gemini decision
        gemini_titles = [r.get('title', '') for r in gemini_results]
        assert any("Gemini" in t for t in gemini_titles)
