import pytest
import numpy as np
from ledgermind.core.reasoning.merging.algorithms.vector_similarity import VectorEmbeddingAlgorithm

class TestVectorEmbeddingAlgorithm:

    @pytest.fixture
    def alg(self):
        return VectorEmbeddingAlgorithm(threshold=0.8, enable_cache=True)

    def test_identical_docs(self, alg):
        """Идентичные документы => similarity 1.0."""
        doc = {'fid': '1', 'title': 'T', 'content': 'C', 'keywords': ['k']}
        sim = alg.calculate_similarity(doc, doc.copy())
        assert sim >= 0.99

    def test_completely_different(self, alg):
        """Разные документы => similarity низкий."""
        doc1 = {'title': 'A', 'content': 'A'}
        doc2 = {'title': 'B', 'content': 'B'}
        sim = alg.calculate_similarity(doc1, doc2)
        assert sim < 0.5

    def test_keyword_boost(self, alg):
        """Общие keywords повышают similarity (с мокированием)."""
        # Используем одинаковый контент, чтобы semantic_sim был 1.0
        doc1 = {'fid': 'a', 'title': 'Same', 'content': 'Same', 'keywords': ['shared', 'k1']}
        doc2 = {'fid': 'b', 'title': 'Same', 'content': 'Same', 'keywords': ['shared', 'k2']}

        alg._ensure_model()
        from unittest.mock import MagicMock
        
        v1 = np.zeros(768); v1[0] = 1.0
        
        # Мок всегда возвращает один и тот же вектор (сходство 1.0)
        alg.embedding_model.encode = MagicMock(return_value=np.array([v1]))
        alg.clear_cache()
        
        # С ключевыми словами (semantic_sim=1.0, kw_sim=1.0)
        sim_with = alg.calculate_similarity(doc1, doc2)

        # Без ключевых слов В ОДНОМ из документов (semantic_sim=1.0, kw_sim=0.5)
        # Если удалить у обоих, ядро вернет kw_sim=1.0 (совпадение отсутствия)
        doc2_nk = {k: v for k, v in doc2.items() if k != 'keywords'}
        alg.clear_cache()
        sim_without = alg.calculate_similarity(doc1, doc2_nk)

        assert sim_with > sim_without

    def test_cache_functionality(self, alg):
        """Кэш возвращает одинаковые значения."""
        doc1 = {'title': 'T', 'content': 'Content', 'fid': '1'}
        doc2 = {'title': 'S', 'content': 'Second', 'fid': '2'}

        sim1 = alg.calculate_similarity(doc1, doc2)
        sim2 = alg.calculate_similarity(doc1, doc2)

        assert sim1 == sim2
        assert ('1', '2') in alg._pairwise_cache

    def test_threshold_filtering(self, alg):
        """Search возвращает только выше порога (с мокированием модели)."""
        candidate = {
            'fid': 'cand',
            'title': 'Machine Learning',
            'content': 'Neural networks',
            'keywords': ['ML']
        }

        all_docs = [
            {'fid': 'd1', 'title': 'Machine Learning', 'content': 'Neural networks', 'keywords': ['ML']},  # идентичная
            {'fid': 'd2', 'title': 'Cooking', 'content': 'Recipes', 'keywords': ['food']},  # низкая
        ]

        alg._ensure_model()
        from unittest.mock import MagicMock
        
        v1 = np.zeros(768); v1[0] = 1.0
        v2 = np.zeros(768); v2[1] = 1.0
        
        def side_effect(texts):
            results = []
            for t in texts:
                if 'Machine Learning' in t or 'ML' in t: results.append(v1)
                else: results.append(v2)
            return np.array(results)
            
        alg.embedding_model.encode = MagicMock(side_effect=side_effect)
        alg.clear_cache()

        class MockMemory:
            class MockSemantic:
                class MockMeta:
                    def list_all(self):
                        return all_docs
                    def get_batch_by_fids(self, fids):
                        return [d for d in all_docs if d['fid'] in fids]
                meta = MockMeta()
            semantic = MockSemantic()
            vector_index = None

        results = alg.search(candidate, MockMemory())
        assert len(results) == 1
        assert results[0]['fid'] == 'd1'
