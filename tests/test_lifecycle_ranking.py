
import os
import shutil
import unittest
from datetime import datetime, timedelta
from ledgermind.core.api.memory import Memory
from ledgermind.core.core.schemas import DecisionStream, DecisionPhase, DecisionVitality, KIND_DECISION

class TestLifecycleRanking(unittest.TestCase):
    def setUp(self):
        self.test_dir = "./temp_test_lifecycle"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)
        self.memory = Memory(storage_path=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_lifecycle_multiplier_ranking(self):
        print("Testing Lifecycle Multiplier Ranking...")
        
        # 1. Create a DORMANT CANONICAL decision
        # We manually use process_event to set these fields since record_decision defaults to EMERGENT/ACTIVE
        ctx_dormant = DecisionStream(
            decision_id="dormant_canonical_fid",
            title="Standard API Authentication",
            target="auth_v1",
            rationale="Legacy authentication patterns that are canonical but no longer active.",
            phase=DecisionPhase.CANONICAL,
            vitality=DecisionVitality.DORMANT,
            namespace="default"
        )
        dec_dormant = self.memory.process_event(
            source="agent",
            kind=KIND_DECISION,
            content="Standard API Authentication",
            context=ctx_dormant
        )
        fid_dormant = dec_dormant.metadata['file_id']

        # 2. Create an ACTIVE EMERGENT decision with the same query profile
        ctx_active = DecisionStream(
            decision_id="active_emergent_fid",
            title="Standard API Authentication",
            target="auth_v2",
            rationale="Modern authentication patterns that are currently emerging and very active.",
            phase=DecisionPhase.EMERGENT,
            vitality=DecisionVitality.ACTIVE,
            namespace="default"
        )
        dec_active = self.memory.process_event(
            source="agent",
            kind=KIND_DECISION,
            content="Standard API Authentication",
            context=ctx_active
        )
        fid_active = dec_active.metadata['file_id']

        # 3. Search
        results = self.memory.search_decisions("Standard API Authentication", limit=10)
        
        res_map = {r['id']: r for r in results}
        score_dormant = res_map[fid_dormant]['score']
        score_active = res_map[fid_active]['score']
        
        print(f"Scores -> Dormant Canonical: {score_dormant:.4f}, Active Emergent: {score_active:.4f}")
        
        # Calculation check:
        # phase_weights = {"canonical": 1.5, "emergent": 1.2, "pattern": 1.0}
        # vitality_weights = {"active": 1.0, "decaying": 0.5, "dormant": 0.2}
        # Multiplier Dormant Canonical = 1.5 * 0.2 = 0.3
        # Multiplier Active Emergent = 1.2 * 1.0 = 1.2
        # Active Emergent should be 4x higher (ignoring vector/keyword differences, which should be minimal here)
        
        self.assertGreater(score_active, score_dormant, "Active Emergent should rank higher than Dormant Canonical")
        print("✓ Lifecycle Ranking OK.")

    def test_intervention_lifecycle(self):
        print("Testing KIND_INTERVENTION Lifecycle...")
        
        # Verify that KIND_INTERVENTION immediately appears in search as EMERGENT with high cost
        content = "Critical security patch for database connection"
        dec = self.memory.process_event(
            source="user",
            kind="intervention",
            content=content,
            context={"target": "db_security"}
        )
        fid = dec.metadata['file_id']
        
        results = self.memory.search_decisions("security patch", limit=1)
        self.assertEqual(len(results), 1)
        res = results[0]
        
        self.assertEqual(res['id'], fid)
        
        # Check metadata in DB
        meta = self.memory.semantic.meta.get_by_fid(fid)
        self.assertEqual(meta['phase'], 'emergent')
        self.assertEqual(meta['vitality'], 'active')
        self.assertGreaterEqual(meta['reinforcement_density'], 0.0)
        
        print("✓ Intervention Lifecycle OK.")

    def test_sql_integrity_columns(self):
        print("Testing SQL Integrity for new columns...")
        import sqlite3
        db_path = os.path.join(self.test_dir, "semantic/semantic_meta.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(semantic_meta)")
        columns = [row[1] for row in cursor.fetchall()]
        
        required_columns = [
            "phase", "vitality", "reinforcement_density", 
            "stability_score", "coverage", "context_json"
        ]
        for col in required_columns:
            self.assertIn(col, columns, f"Column {col} missing from semantic_meta table")
        
        conn.close()
        print("✓ SQL Integrity OK.")

if __name__ == "__main__":
    unittest.main()
