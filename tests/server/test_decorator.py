import pytest
from unittest.mock import MagicMock, patch, ANY
import time
import os
import sys

# Mock dependencies to avoid actual imports if they are heavy or missing
# sys.modules['ledgermind.core.api.bridge'] = MagicMock()
# sys.modules['ledgermind.server.background'] = MagicMock()

from ledgermind.server.server import MCPServer
from ledgermind.server.contracts import RecordDecisionRequest, DecisionResponse, SupersedeDecisionRequest, SearchDecisionsRequest, SearchResponse

class TestDecorator:
    @pytest.fixture
    def server(self):
        memory = MagicMock()
        # Mocking __init__ dependencies
        with patch('ledgermind.server.server.EnvironmentContext'), \
             patch('ledgermind.server.server.AuditLogger'), \
             patch('ledgermind.server.server.FastMCP'):
            server = MCPServer(memory, start_worker=False)
            server.audit_logger = MagicMock()
            # Mocking _get_commit_hash as it is used in logging
            server._get_commit_hash = MagicMock(return_value="abc1234")
            # Mocking _check_capability
            server._check_capability = MagicMock()
            # Mocking _validate_auth
            server._validate_auth = MagicMock()
            # Mocking _apply_cooldown
            server._apply_cooldown = MagicMock()
            # Mocking _validate_isolation
            server._validate_isolation = MagicMock()

            return server

    def test_handle_record_decision_success(self, server):
        req = RecordDecisionRequest(title="Test", target="Target", rationale="Short but valid rationale", consequences=[], namespace="default")
        server.memory.record_decision.return_value.metadata = {"file_id": "dec_123"}

        with patch('ledgermind.server.server.TOOL_CALLS') as mock_calls, \
             patch('ledgermind.server.server.TOOL_LATENCY') as mock_latency:

            mock_calls.labels.return_value = MagicMock()
            mock_latency.labels.return_value = MagicMock()

            resp = server.handle_record_decision(req)

            assert resp.status == "success"
            assert resp.decision_id == "dec_123"

            # Check Metrics
            mock_calls.labels.assert_called_with(tool="record_decision", status="success")
            mock_latency.labels.assert_called_with(tool="record_decision")

            # Check Audit Log
            server.audit_logger.log_access.assert_called_with(
                "agent", "record_decision", req.model_dump(), True, commit_hash="abc1234"
            )

    def test_handle_record_decision_failure(self, server):
        req = RecordDecisionRequest(title="Test", target="Target", rationale="Short but valid rationale", consequences=[], namespace="default")
        server.memory.record_decision.side_effect = Exception("Memory Error")

        with patch('ledgermind.server.server.TOOL_CALLS') as mock_calls, \
             patch('ledgermind.server.server.TOOL_LATENCY') as mock_latency:

            mock_calls.labels.return_value = MagicMock()
            mock_latency.labels.return_value = MagicMock()

            resp = server.handle_record_decision(req)

            assert resp.status == "error"
            assert "Memory Error" in resp.message

            # Check Metrics
            mock_calls.labels.assert_called_with(tool="record_decision", status="error")
            mock_latency.labels.assert_called_with(tool="record_decision")

            # Check Audit Log
            server.audit_logger.log_access.assert_called_with(
                "agent", "record_decision", req.model_dump(), False, error="Memory Error"
            )

    def test_handle_supersede_decision_success(self, server):
        req = SupersedeDecisionRequest(title="Test", target="Target", rationale="Short valid rationale for supersede", old_decision_ids=["old_1"], consequences=[], namespace="default")
        server.memory.supersede_decision.return_value.metadata = {"file_id": "dec_456"}

        with patch('ledgermind.server.server.TOOL_CALLS') as mock_calls, \
             patch('ledgermind.server.server.TOOL_LATENCY') as mock_latency:

            mock_calls.labels.return_value = MagicMock()
            mock_latency.labels.return_value = MagicMock()

            resp = server.handle_supersede_decision(req)

            assert resp.status == "success"
            assert resp.decision_id == "dec_456"

            # Check Audit Log - Should include commit hash
            server.audit_logger.log_access.assert_called_with(
                "agent", "supersede_decision", req.model_dump(), True, commit_hash="abc1234"
            )

    def test_handle_search_success(self, server):
        req = SearchDecisionsRequest(query="Test", limit=5)
        server.memory.search_decisions.return_value = []

        with patch('ledgermind.server.server.TOOL_CALLS') as mock_calls, \
             patch('ledgermind.server.server.TOOL_LATENCY') as mock_latency:

            mock_calls.labels.return_value = MagicMock()
            mock_latency.labels.return_value = MagicMock()

            resp = server.handle_search(req)

            assert resp.status == "success"
            assert resp.results == []

            # Check Audit Log - Should NOT include commit hash (default None)
            server.audit_logger.log_access.assert_called_with(
                "agent", "search_decisions", req.model_dump(), True, commit_hash=None
            )

    def test_handle_record_decision_redaction(self, server):
        # Long rationale that should be redacted
        long_rationale = "This is a very long rationale that should definitely be redacted by the new redaction helper we just implemented."
        req = RecordDecisionRequest(title="Test", target="Target", rationale=long_rationale, consequences=[], namespace="default")
        server.memory.record_decision.return_value.metadata = {"file_id": "dec_123"}

        with patch('ledgermind.server.server.TOOL_CALLS'), \
             patch('ledgermind.server.server.TOOL_LATENCY'):

            server.handle_record_decision(req)

            # Extract the actual data passed to log_access
            call_args = server.audit_logger.log_access.call_args[0]
            req_dump = call_args[2]

            assert "[REDACTED]" in req_dump["rationale"]
            assert len(req_dump["rationale"]) < len(long_rationale)
