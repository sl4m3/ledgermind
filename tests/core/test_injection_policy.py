import os
import shutil
import unittest
from unittest.mock import MagicMock, patch
from ledgermind.core.api.bridge import IntegrationBridge

class TestInjectionPolicy(unittest.TestCase):
    """
    Tests for the LedgerMind context injection policy:
    1. Relevance threshold (0.65).
    2. Context window retention (10 turns).
    3. Injection suppression while window is active.
    """
    def setUp(self):
        self.test_dir = "./temp_test_injection_policy"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        
        # Initialize bridge with high threshold (0.65) and 10 turns retention
        self.bridge = IntegrationBridge(
            memory_path=self.test_dir, 
            relevance_threshold=0.65, 
            retention_turns=10
        )
        
        self.high_memory = {
            "id": "high.md", 
            "score": 0.8, 
            "title": "High Relevance", 
            "preview": "Important knowledge"
        }
        self.low_memory = {
            "id": "low.md", 
            "score": 0.4, 
            "title": "Low Relevance", 
            "preview": "Irrelevant noise"
        }

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_relevance_threshold(self):
        """Verify that only memories above the threshold are selected for injection."""
        self.bridge._memory.search_decisions = MagicMock(
            return_value=[self.high_memory, self.low_memory]
        )
        
        memories = self.bridge._find_relevant_memories("test query")
        
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]['id'], "high.md")

    @patch("subprocess.Popen")
    def test_sliding_window_suppression(self, mock_popen):
        """Verify that new injections are suppressed until the previous ones exit the window."""
        # Setup mock process with enough output for all turns
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["Response Data"] * 20)
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc
        
        # Memory to be injected
        self.bridge._memory.search_decisions = MagicMock(return_value=[self.high_memory])
        
        # --- Turn 1: Context is empty, SHOULD inject ---
        self.bridge.execute_with_memory(["echo"], "Query 1")
        args_1, _ = mock_popen.call_args
        self.assertIn("[LEDGERMIND KNOWLEDGE BASE ACTIVE]", args_1[0][-1])
        
        # --- Turns 2-10: Context window is active, SHOULD NOT inject ---
        for i in range(2, 11):
            mock_popen.reset_mock()
            self.bridge.execute_with_memory(["echo"], f"Query {i}")
            args, _ = mock_popen.call_args
            # Verify that the knowledge block is NOT present in the prompt sent to CLI
            self.assertNotIn("[LEDGERMIND KNOWLEDGE BASE ACTIVE]", args[0][-1])
            
        # --- Turn 11: Window for Turn 1 (retention=10) expires, SHOULD inject ---
        mock_popen.reset_mock()
        self.bridge.execute_with_memory(["echo"], "Query 11")
        args_11, _ = mock_popen.call_args
        self.assertIn("[LEDGERMIND KNOWLEDGE BASE ACTIVE]", args_11[0][-1])

if __name__ == "__main__":
    unittest.main()
