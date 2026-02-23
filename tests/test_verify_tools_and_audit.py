
import os
import shutil
import unittest
import json
import time
import logging
from ledgermind.core.api.memory import Memory
from ledgermind.server.server import MCPServer

class TestTools(unittest.TestCase):
    def setUp(self):
        self.test_dir = "./temp_test_tools"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        self.memory = Memory(storage_path=self.test_dir)
        
        # Patch BackgroundWorker to avoid SQLite concurrency issues in unit tests
        self.patcher = unittest.mock.patch("ledgermind.server.background.BackgroundWorker.start")
        self.patcher.start()
        
        self.server = MCPServer(self.memory, storage_path=self.test_dir)

    def tearDown(self):
        self.patcher.stop()
        # Shutdown any logging handlers to free files
        for handler in logging.getLogger("agent_memory_audit").handlers[:]:
            handler.close()
            logging.getLogger("agent_memory_audit").removeHandler(handler)
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_audit_logs_tool(self):
        print("Testing Audit Logs Tool...")
        # 1. Trigger some activity
        class MockRequest:
            def __init__(self, query, limit, mode):
                self.query = query
                self.limit = limit
                self.mode = mode
            def model_dump(self):
                return {"query": self.query, "limit": self.limit, "mode": self.mode}

        self.server.handle_search(MockRequest('test search query long enough', 1, 'balanced'))
        time.sleep(1)
        
        # 2. Get logs via tool logic
        logs = self.server.audit_logger.get_logs(limit=5)
        self.assertGreater(len(logs), 0, "Audit logs should contain records")
        logs_str = "".join(logs)
        self.assertIn("search_decisions", logs_str)
        print("✓ Audit Logs OK.")

    def test_decision_history(self):
        print("Testing Decision History (Git integration)...")
        dec = self.memory.record_decision("Evolution Decision Title", "evolution", "Initial version rationale long enough")
        fid = dec.metadata['file_id']
        
        # 2. Update it
        self.memory.supersede_decision("Evolution v2 Title", "evolution", "Updated version rationale long enough", [fid])
        
        # 3. Check history
        history = self.memory.get_decision_history(fid)
        self.assertGreaterEqual(len(history), 1, "Should show git history for the file")
        print(f"History entries: {len(history)}")
        print("✓ Decision History OK.")

    def test_api_specification(self):
        print("Testing API Specification Tool...")
        from ledgermind.server.specification import MCPApiSpecification
        spec = MCPApiSpecification.generate_full_spec()
        self.assertEqual(spec['mcp_api_version'], "2.7.6")
        self.assertIn("record_decision", spec['tools'])
        print("✓ API Specification OK.")

if __name__ == "__main__":
    unittest.main()
