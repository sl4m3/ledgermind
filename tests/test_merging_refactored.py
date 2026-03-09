import unittest
from unittest.mock import MagicMock
from ledgermind.core.reasoning.merging import MergeEngineFacade, MergeConfig
from ledgermind.core.reasoning.merging.validator import DuplicateValidator

class TestMergingRefactoring(unittest.TestCase):
    def setUp(self):
        self.memory = MagicMock()
        self.config = MergeConfig(threshold=0.8)
        self.facade = MergeEngineFacade(self.memory, self.config)

    def test_validator_candidate(self):
        valid_candidate = {
            "title": "Test Title",
            "content": "Test Content",
            "keywords": ["test"],
            "target": "test_target"
        }
        error = DuplicateValidator.validate_candidate(valid_candidate)
        self.assertIsNone(error)

        invalid_candidate = {"title": "Only Title"}
        error = DuplicateValidator.validate_candidate(invalid_candidate)
        self.assertIsNotNone(error)

    def test_facade_initialization(self):
        self.assertEqual(self.facade.config.threshold, 0.8)
        self.assertIsNotNone(self.facade.algorithm)
        self.assertIsNotNone(self.facade.transaction_manager)

if __name__ == '__main__':
    unittest.main()
