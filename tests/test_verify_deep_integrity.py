
import os
import shutil
import unittest
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.exceptions import InvariantViolation

class TestDeepIntegrity(unittest.TestCase):
    def setUp(self):
        self.test_dir = "./temp_test_integrity"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        self.memory = Memory(storage_path=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_conflict_prevention(self):
        print("Testing Conflict Prevention (Invariant I4)...")
        # 1. Create decision
        self.memory.record_decision("Original Decision Title", "target_1", "Rationale that is long enough to pass validation")
        
        # 2. Try to create another for same target - should be blocked
        try:
            self.memory.record_decision("Totally Different Strategy", "target_1", "This is a completely unrelated rationale that should not trigger auto-supersede.")
            self.fail("Should have blocked conflicting decision")
        except Exception as e:
            self.assertIn("CONFLICT", str(e))
            print(f"✓ Conflict correctly blocked: {e}")

    def test_transition_validation(self):
        print("Testing Transition Validation (Immutability)...")
        dec = self.memory.record_decision("Immutability Test Title", "target_2", "Original rationale that is long enough")
        fid = dec.metadata['file_id']
        
        # Try to change 'target' in an existing decision - should be blocked by TransitionValidator
        try:
            self.memory.semantic.update_decision(fid, {"target": "illegal_change"}, "Hacking target with long enough msg")
            self.fail("Should have blocked immutable field change")
        except Exception as e:
            self.assertIn("I1 Violation", str(e))
            print(f"✓ Illegal transition blocked: {e}")

    def test_orphan_cleanup(self):
        print("Testing Automatic Orphan (Ghost) Cleanup...")
        self.memory.record_decision("To be ghosted decision", "target_3", "Rationale that is long enough")
        fids = self.memory.get_decisions()
        fid = fids[0]
        
        # Manually delete file
        os.remove(os.path.join(self.memory.semantic.repo_path, fid))
        
        # Run maintenance (syncs meta)
        self.memory.run_maintenance()
        
        self.assertNotIn(fid, self.memory.get_decisions(), "Orphaned record should be removed from MetaStore")
        print("✓ Orphan cleanup OK.")

if __name__ == "__main__":
    unittest.main()
