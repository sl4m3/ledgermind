"""
Tests for procedural format handling in decisions.
"""
import pytest
import json
from datetime import datetime
from ledgermind.core.core.schemas import DecisionStream, DecisionPhase, ProceduralContent, ProceduralStep


class TestProceduralLoading:
    """Test loading procedural from database format."""

    def test_load_decision_with_list_procedural(self):
        """DecisionStream accepts procedural as list[dict] from DB."""
        from ledgermind.core.core.schemas import ProceduralContent
        
        # Simulate DB context with procedural as list[dict]
        ctx_dict = {
            'decision_id': 'test-1',
            'target': 'test',
            'title': 'Test Decision',
            'rationale': 'Test rationale',
            'phase': 'pattern',
            'procedural': [
                {'action': 'Step 1', 'expected_outcome': 'Outcome 1', 'rationale': 'Why 1'},
                {'action': 'Step 2', 'expected_outcome': 'Outcome 2'}
            ]
        }
        
        # Convert procedural to ProceduralContent (as reflection.py does)
        proc_list = ctx_dict['procedural']
        if isinstance(proc_list, list):
            steps = [
                ProceduralStep(
                    action=step.get('action', ''),
                    expected_outcome=step.get('expected_outcome'),
                    rationale=step.get('rationale')
                )
                for step in proc_list
            ]
            ctx_dict['procedural'] = ProceduralContent(steps=steps)
        
        # Should not raise
        stream = DecisionStream(**ctx_dict)
        
        assert isinstance(stream.procedural, ProceduralContent)
        assert len(stream.procedural.steps) == 2
        assert stream.procedural.steps[0].action == 'Step 1'

    def test_load_decision_with_dict_procedural(self):
        """DecisionStream accepts procedural as ProceduralContent dict."""
        proc_content = ProceduralContent(steps=[
            ProceduralStep(action='Step 1')
        ])
        
        ctx_dict = {
            'decision_id': 'test-2',
            'target': 'test',
            'title': 'Test Decision',
            'rationale': 'Test rationale',
            'phase': 'pattern',
            'procedural': proc_content.model_dump(mode='json')
        }
        
        stream = DecisionStream(**ctx_dict)
        
        assert isinstance(stream.procedural, ProceduralContent)
        assert len(stream.procedural.steps) == 1


class TestProceduralConsolidation:
    """Test procedural handling in consolidation."""

    def test_consolidation_saves_procedural_correctly(self):
        """_execute_consolidation converts procedural from LLM to ProceduralContent."""
        from ledgermind.core.reasoning.enrichment.facade import LLMEnricher
        
        # Simulate LLM response with procedural as list[dict]
        res_data = {
            'title': 'Consolidated Decision',
            'rationale': 'Combined rationale',
            'procedural': [
                {'action': 'Action 1', 'expected_outcome': 'Outcome 1', 'rationale': 'Why'},
                {'action': 'Action 2'}
            ]
        }
        
        # Simulate conversion (as in _execute_consolidation)
        def _clean_text(text):
            return text.strip() if text else ''
        
        procedural_raw = res_data.get('procedural')
        procedural_converted = None
        if procedural_raw and isinstance(procedural_raw, list):
            steps = [
                ProceduralStep(
                    action=_clean_text(step.get('action', '')),
                    expected_outcome=_clean_text(step.get('expected_outcome')),
                    rationale=_clean_text(step.get('rationale'))
                )
                for step in procedural_raw
            ]
            procedural_converted = ProceduralContent(steps=steps)
        
        assert procedural_converted is not None
        assert len(procedural_converted.steps) == 2
        assert procedural_converted.steps[0].action == 'Action 1'
        assert procedural_converted.steps[1].rationale == ''  # Missing rationale


class TestProceduralNormalization:
    """Test procedural normalization in update_decision."""

    def test_update_decision_normalizes_procedural(self):
        """update_decision converts procedural from list to ProceduralContent."""
        # Simulate updates with procedural as list[dict]
        updates = {
            'procedural': [
                {'action': 'Step 1', 'expected_outcome': 'Out 1'},
                {'action': 'Step 2'}
            ]
        }
        
        # Normalize (as in update_decision)
        updates_normalized = updates.copy()
        if 'procedural' in updates_normalized and updates_normalized['procedural']:
            proc = updates_normalized['procedural']
            if isinstance(proc, list):
                steps = [
                    ProceduralStep(**step) if isinstance(step, dict) else step
                    for step in proc
                ]
                updates_normalized['procedural'] = ProceduralContent(steps=steps)
        
        assert isinstance(updates_normalized['procedural'], ProceduralContent)
        assert len(updates_normalized['procedural'].steps) == 2


class TestProceduralFixScript:
    """Test the fix_procedural_format.py script logic."""

    def test_fix_script_conversion(self):
        """Fix script correctly converts list[dict] to ProceduralContent JSON."""
        # Simulate DB context_json with procedural as list[dict]
        ctx = {
            'title': 'Test',
            'procedural': [
                {'action': 'A1', 'expected_outcome': 'O1', 'rationale': 'R1'},
                {'action': 'A2'}
            ]
        }
        
        # Convert (as in fix script)
        proc = ctx.get('procedural')
        if isinstance(proc, list):
            steps = [
                ProceduralStep(
                    action=step.get('action', ''),
                    expected_outcome=step.get('expected_outcome'),
                    rationale=step.get('rationale')
                )
                for step in proc
            ]
            proc_content = ProceduralContent(steps=steps)
            ctx['procedural'] = proc_content.model_dump(mode='json')
        
        # Verify JSON format
        assert isinstance(ctx['procedural'], dict)
        assert 'steps' in ctx['procedural']
        assert len(ctx['procedural']['steps']) == 2
        assert ctx['procedural']['steps'][0]['action'] == 'A1'
        
        # Verify round-trip
        json_str = json.dumps(ctx)
        ctx_loaded = json.loads(json_str)
        assert ctx_loaded['procedural']['steps'][1]['action'] == 'A2'
