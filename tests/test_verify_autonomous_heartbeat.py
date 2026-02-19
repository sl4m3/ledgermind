
import os
import shutil
import unittest
import time
from ledgermind.core.api.memory import Memory
from ledgermind.server.server import MCPServer
from ledgermind.core.core.schemas import TrustBoundary

class TestHeartbeat(unittest.TestCase):
    def setUp(self):
        self.test_dir = "./temp_test_heartbeat"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        self.memory = Memory(storage_path=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_persistent_timers(self):
        print("
Testing Persistent Timers across restarts...")
        # 1. Set a fake "last run" time in the past (e.g., 20 hours ago)
        twenty_hours_ago = time.time() - (20 * 3600)
        self.memory.semantic.meta.set_config("last_git_gc_time", twenty_hours_ago)
        
        # 2. Start server
        server = MCPServer(self.memory, storage_path=self.test_dir)
        print("Waiting 35s for startup tasks...")
        time.sleep(35) # Wait for startup tasks
        
        # 3. Git GC should NOT have run yet (since 24h haven't passed)
        last_gc_val = self.memory.semantic.meta.get_config("last_git_gc_time")
        last_gc = float(last_gc_val) if last_gc_val else 0.0
        self.assertEqual(last_gc, twenty_hours_ago, "Git GC timer should persist and NOT reset on startup")
        
        # 4. Reflection SHOULD have run because it's a startup recovery task
        last_ref = self.memory.semantic.meta.get_config("last_reflection_time")
        self.assertIsNotNone(last_ref, "Reflection should run on startup regardless of timer for recovery")
        print("✓ Persistent Timers and Startup Recovery OK.")

if __name__ == "__main__":
    unittest.main()
