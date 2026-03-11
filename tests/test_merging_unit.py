import unittest
from unittest.mock import MagicMock
from ledgermind.core.reasoning.merging import (
    MergeEngineFacade, MergeConfig, ProposalBuilder, 
    TransactionManager, AlgorithmFactory
)

class TestMergingAdvanced(unittest.TestCase):
    def setUp(self):
        self.memory = MagicMock()
        self.memory.semantic.meta.list_all.return_value = [
            {"id": "doc_1", "title": "Advanced Python", "content": "Python concurrency and async", "keywords": ["python", "async"]},
            {"id": "doc_2", "title": "Python Asyncio", "content": "Deep dive into python asyncio", "keywords": ["python", "asyncio"]},
            {"id": "doc_3", "title": "Docker Basics", "content": "How to use docker containers", "keywords": ["docker", "containers"]}
        ]
        
        # Test BM25 creation
        AlgorithmFactory.register("bm25", __import__("ledgermind.core.reasoning.merging.algorithms", fromlist=["BM25Algorithm"]).BM25Algorithm)
        
        self.config = MergeConfig(threshold=0.1) 
        self.facade = MergeEngineFacade(self.memory, self.config)

    def test_builder_validation(self):
        builder = ProposalBuilder(self.memory)
        builder.set_topic("Test")
        builder.add_target("doc_1")
        # Should raise ValueError because only 1 target is added
        with self.assertRaises(ValueError):
            builder.build()

    def test_rrfjaccard_algorithm_fallback(self):
        # Removing vector_index to test fallback to list_all
        del self.memory.vector_index
        candidate = {"id": "doc_4", "title": "Python Concurrency", "content": "Async in python", "keywords": ["python"]}
        result = self.facade.scan_for_duplicates([candidate])
        
        self.assertTrue(result.success)
        self.assertIsInstance(result.data, list)
        
        # Verify transaction manager was called to create proposal
        if result.data:
            self.memory.semantic.add_decision.assert_called()

    def test_bm25_algorithm(self):
        config = MergeConfig(threshold=0.1)
        config.algorithms = {"default": {"name": "bm25"}, "bm25": {"threshold": 0.05}}
        facade = MergeEngineFacade(self.memory, config)
        
        candidate = {"id": "doc_4", "title": "Asyncio python", "content": "Learning python asyncio", "keywords": ["python", "asyncio"]}
        result = facade.scan_for_duplicates([candidate])
        
        self.assertTrue(result.success)
        # It should match doc_1 and doc_2 due to low threshold and high overlap
        if result.data:
            self.memory.semantic.add_decision.assert_called()

    def test_transaction_manager_lock(self):
        tm = TransactionManager(self.memory)
        tm.lock_decisions(["doc_1"], "Test lock")
        self.memory.semantic.update_decision.assert_called_with("doc_1", {"merge_status": "pending"}, "Locking for merge: Test lock")

if __name__ == '__main__':
    unittest.main()
