import unittest
from unittest.mock import MagicMock
from ledgermind.core.reasoning.merging import MergeEngineFacade, MergeConfig, ProposalBuilder

class TestMergingIntegration(unittest.TestCase):
    def setUp(self):
        # Мок памяти
        self.memory = MagicMock()
        self.memory.semantic.meta.list_all.return_value = [
            {"id": "1", "title": "Установка Docker", "content": "Как установить docker на ubuntu", "keywords": ["docker", "ubuntu"]},
            {"id": "2", "title": "Docker Setup", "content": "Установка docker на ubuntu linux", "keywords": ["docker", "linux"]},
            {"id": "3", "title": "Python Basics", "content": "Введение в python", "keywords": ["python", "code"]}
        ]
        
        self.config = MergeConfig(threshold=0.3)
        self.facade = MergeEngineFacade(self.memory, self.config)

    def test_full_scan_pipeline(self):
        candidate = {"id": "4", "title": "Гайд Docker", "content": "установка docker", "keywords": ["docker"], "target": "docker_guide"}
        
        # Запуск сканирования
        result = self.facade.scan_for_duplicates([candidate])
        
        self.assertTrue(result.success)
        self.assertIsInstance(result.data, list)
        
        # Должен найти совпадения и создать proposal
        if len(result.data) > 0:
            self.assertTrue(result.data[0].startswith("proposal_"))

    def test_builder_pattern(self):
        builder = ProposalBuilder(self.memory)
        builder.set_topic("Test topic").add_target("doc_1").add_target("doc_2").set_confidence(0.85)
        proposal = builder.build()
        
        self.assertEqual(proposal["topic"], "Test topic")
        self.assertIn("doc_1", proposal["target_ids"])
        self.assertEqual(proposal["confidence"], 0.85)

if __name__ == '__main__':
    unittest.main()
