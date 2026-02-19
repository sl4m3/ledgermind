
import os
import shutil
import unittest
from ledgermind.core.api.memory import Memory

class TestGroundedRanking(unittest.TestCase):
    def setUp(self):
        self.test_dir = "./temp_test_ranking"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        self.memory = Memory(storage_path=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_evidence_boost(self):
        print("Testing Evidence-based Ranking Boost...")
        # 1. Create two similar decisions
        dec1 = self.memory.record_decision("Network Policy A Title", "net_a", "Standard security rationale long enough")
        dec2 = self.memory.record_decision("Network Policy B Title", "net_b", "Standard security rationale long enough")
        
        fid1 = dec1.metadata['file_id']
        fid2 = dec2.metadata['file_id']
        
        # 2. Add evidence (links) only to dec2
        for i in range(10):
            # Record some interactions and link them to dec2
            ev = self.memory.process_event("user", "prompt", f"Check net interaction {i}")
            ev_id = ev.metadata['event_id']
            self.memory.link_evidence(ev_id, fid2)
            
        # 3. Search - dec2 should have a higher score than dec1 due to evidence boost
        results = self.memory.search_decisions("Standard security", limit=10)
        
        # Sort results by score to check order
        res_map = {r['id']: r for r in results}
        score1 = res_map[fid1]['score']
        score2 = res_map[fid2]['score']
        
        print(f"Scores -> Dec1 (0 links): {score1:.4f}, Dec2 (10 links): {score2:.4f}")
        self.assertGreater(score2, score1, "Decision with evidence should have a higher score")
        print("✓ Grounded Ranking Boost OK.")

if __name__ == "__main__":
    unittest.main()
