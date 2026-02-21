
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
        print("Testing Persistent Timers across restarts (Sequential)...")
        # 0. Add at least one episodic event so reflection has something to do
        from ledgermind.core.core.schemas import MemoryEvent
        self.memory.episodic.append(MemoryEvent(source="system", kind="result", content="Initial event"))

        # 1. Set a fake "last run" time in the past (e.g., 20 hours ago)
        twenty_hours_ago = time.time() - (20 * 3600)
        self.memory.semantic.meta.set_config("last_git_gc_time", twenty_hours_ago)
        
        # 2. Start server without auto-starting background thread
        server = MCPServer(self.memory, storage_path=self.test_dir, start_worker=False)
        
        # 3. Manually trigger internal worker tasks sequentially
        print("Manually triggering startup/maintenance tasks...")
        server.worker._run_health_check()
        server.worker._run_git_sync()
        server.worker._run_reflection()
        
        # 4. Git GC should NOT have run yet (since 24h haven't passed)
        last_gc_val = self.memory.semantic.meta.get_config("last_git_gc_time")
        last_gc = float(last_gc_val) if last_gc_val else 0.0
        self.assertEqual(last_gc, twenty_hours_ago, "Git GC timer should persist and NOT reset on manual run")
        
        # 5. Reflection SHOULD have run because we triggered it manually
        # We check for the new key: last_reflection_event_id
        last_ref_id = self.memory.semantic.meta.get_config("last_reflection_event_id")
        self.assertIsNotNone(last_ref_id, "Reflection should run to index existing episodic events")
        print("✓ Persistent Timers and Startup Recovery OK.")

if __name__ == "__main__":
    unittest.main()
