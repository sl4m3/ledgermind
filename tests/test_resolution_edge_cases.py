import os
import shutil
import unittest
from datetime import datetime
from ledgermind.core.api.memory import Memory

class TestResolutionEdgeCases(unittest.TestCase):
    def setUp(self):
        self.test_dir = "./temp_test_resolution"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        self.memory = Memory(storage_path=self.test_dir)

    def tearDown(self):
        self.memory.close()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_broken_link_chain(self):
        """Verify that a broken link in the chain results in None."""
        print("Testing Broken Link Chain...")

        # Create A
        dec_a = self.memory.record_decision("A", "target_a", "Rationale A must be long enough to pass validation.")
        fid_a = dec_a.metadata['file_id']

        # Create B superseding A
        dec_b = self.memory.supersede_decision("B", "target_a", "Rationale B must be long enough to pass validation.", [fid_a])
        fid_b = dec_b.metadata['file_id']

        # Create C superseding B
        dec_c = self.memory.supersede_decision("C", "target_a", "Rationale C must be long enough to pass validation.", [fid_b])
        fid_c = dec_c.metadata['file_id']

        # Verify A resolves to C
        res = self.memory._resolve_to_truth(fid_a, mode="balanced")
        self.assertIsNotNone(res)
        self.assertEqual(res['fid'], fid_c)

        # Now artificially break the chain by deleting C from metadata
        self.memory.semantic.meta.delete(fid_c)

        # A resolves to B, which points to C (missing). Should return B (the last valid link).
        res_broken = self.memory._resolve_to_truth(fid_a, mode="balanced")
        self.assertIsNotNone(res_broken)
        self.assertEqual(res_broken['fid'], fid_b)

    def test_depth_limit(self):
        """Verify that a chain longer than 20 results in None."""
        print("Testing Depth Limit...")

        current_fid = None
        first_fid = None

        # Create chain of 22 items (0 to 21)
        # 0 -> 1 -> ... -> 21

        dec = self.memory.record_decision("0", "target_depth", "Start must be long enough to pass validation.")
        current_fid = dec.metadata['file_id']
        first_fid = current_fid

        for i in range(1, 22):
            new_dec = self.memory.supersede_decision(f"{i}", "target_depth", f"Superseding {i-1} with enough text for validation.", [current_fid])
            current_fid = new_dec.metadata['file_id']

        # Try to resolve first_fid. Depth is 21. Should return None.
        res = self.memory._resolve_to_truth(first_fid, mode="balanced")
        self.assertIsNone(res, "Should return None when depth limit exceeded")

    def test_circular_dependency(self):
        """Verify circular dependency is handled by depth limit or just works until limit."""
        print("Testing Circular Dependency...")

        # A -> B -> A
        dec_a = self.memory.record_decision("A", "target_circle", "Rationale A must be long enough to pass validation.")
        fid_a = dec_a.metadata['file_id']

        dec_b = self.memory.supersede_decision("B", "target_circle", "Rationale B must be long enough to pass validation.", [fid_a])
        fid_b = dec_b.metadata['file_id']

        # Manually force B to be superseded by A to create circle in metadata
        # B is currently active. A is superseded by B.
        # We want B to be superseded by A.
        self.memory.semantic.meta.upsert(
            fid=fid_b,
            target="target_circle",
            title="B",
            status="superseded",
            kind="decision",
            timestamp=datetime.now(),
            superseded_by=fid_a,
            content="Some content", # content is required
            keywords="",
            confidence=1.0,
            context_json="{}"
        )

        # Now A -> B -> A -> B ...
        # Resolution should hit depth limit and return None.
        res = self.memory._resolve_to_truth(fid_a, mode="balanced")
        self.assertIsNone(res)

if __name__ == "__main__":
    unittest.main()
