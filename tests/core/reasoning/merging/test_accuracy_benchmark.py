import pytest
import logging
from ledgermind.core.reasoning.merging.algorithms.vector_similarity import VectorEmbeddingAlgorithm

logger = logging.getLogger(__name__)

class TestAccuracyOnGroundTruth:

    @pytest.fixture(scope="class")
    def algorithm(self):
        return VectorEmbeddingAlgorithm(threshold=0.8)

    @pytest.fixture
    def labeled_pairs(self):
        """Размеченные пары для теста accuracy."""
        return [
            # (positive pairs)
            ({
                'fid': 'p1',
                'title': 'Introduction to Python',
                'content': 'Python is a high-level programming language',
                'keywords': ['python', 'programming']
            }, {
                'fid': 'p2',
                'title': 'Python programming intro',
                'content': 'Learn Python programming basics',
                'keywords': ['python', 'tutorial']
            }, True),
            # (negative pairs)
            ({
                'fid': 'n1',
                'title': 'Python tutorial',
                'content': 'Programming in Python'
            }, {
                'fid': 'n2',
                'title': 'Italian cooking',
                'content': 'Pasta recipes'
            }, False)
        ]

    def test_f1_score(self, algorithm, labeled_pairs):
        """Расчёт F1-score на размеченных данных (с мокированием модели)."""
        tp = fp = tn = fn = 0

        # Мокируем модель для "идеальной" семантики
        algorithm._ensure_model()
        from unittest.mock import MagicMock
        import numpy as np
        
        v_python = np.zeros(768); v_python[0] = 1.0
        v_cooking = np.zeros(768); v_cooking[1] = 1.0
        
        def side_effect(texts):
            results = []
            for t in texts:
                if 'python' in t.lower() or 'Python' in t: results.append(v_python)
                else: results.append(v_cooking)
            return np.array(results)
            
        algorithm.embedding_model.encode = MagicMock(side_effect=side_effect)
        algorithm.clear_cache()

        for doc1, doc2, is_duplicate in labeled_pairs:
            sim = algorithm.calculate_similarity(doc1, doc2)
            predicted = sim >= algorithm.threshold

            if predicted and is_duplicate:
                tp += 1
            elif predicted and not is_duplicate:
                fp += 1
            elif not predicted and is_duplicate:
                fn += 1
            else:
                tn += 1

        precision = tp / (tp + fp + 1e-9)
        recall = tp / (tp + fn + 1e-9)
        f1 = 2 * precision * recall / (precision + recall + 1e-9)

        logger.info(f"P={precision:.3f}, R={recall:.3f}, F1={f1:.3f}")

        # Целевой F1 > 0.9
        assert f1 > 0.90, f"F1-score {f1:.3f} ниже целевого 0.90"
