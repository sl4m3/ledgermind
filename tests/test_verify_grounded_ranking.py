
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
        self.memory = Memory(storage_path=self.test_dir, vector_model="all-MiniLM-L6-v2")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_evidence_boost(self):
        print("Testing Evidence-based Ranking Boost...")
        from ledgermind.core.core.schemas import KIND_PROPOSAL, MemoryEvent
        
        # 1. Create two similar proposals (Kind boost 1.0)
        prop1 = MemoryEvent(
            source="agent", kind=KIND_PROPOSAL, content="Network Policy A",
            context={"title": "Network Policy A", "target": "net", "rationale": "Rationale A longer than 10", "status": "draft", "confidence": 0.5}
        )
        prop2 = MemoryEvent(
            source="agent", kind=KIND_PROPOSAL, content="Network Policy B",
            context={"title": "Network Policy B", "target": "net", "rationale": "Rationale B longer than 10", "status": "draft", "confidence": 0.5}
        )
        
        fid1 = self.memory.semantic.save(prop1)
        fid2 = self.memory.semantic.save(prop2)
        
        # 2. Add some evidence (links) only to prop2
        for i in range(3):
            ev = self.memory.process_event("user", "prompt", f"Grounded interaction {i}")
            ev_id = ev.metadata['event_id']
            self.memory.link_evidence(ev_id, fid2)
            
        # 3. Search - prop2 should have a higher score than prop1 due to evidence boost
        results = self.memory.search_decisions("network policy", limit=10, mode="audit")
        
        # Sort results by score to check order
        res_map = {r['id']: r for r in results}
        score1 = res_map[fid1]['score']
        score2 = res_map[fid2]['score']
        
        print(f"Scores -> Dec1 (0 links): {score1:.4f}, Dec2 (10 links): {score2:.4f}")
        self.assertGreater(score2, score1, "Decision with evidence should have a higher score")
        print("✓ Grounded Ranking Boost OK.")

if __name__ == "__main__":
    unittest.main()
