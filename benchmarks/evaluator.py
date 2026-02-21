import numpy as np
from typing import List, Dict, Any, Optional

class MetricsCalculator:
    """Calculates Information Retrieval (IR) metrics like Recall, Precision, and MRR."""
    
    @staticmethod
    def recall_at_k(retrieved_ids: List[str], ground_truth_id: str, k: int) -> float:
        """Recall@K: 1.0 if the correct ID is in top K, else 0.0."""
        return 1.0 if ground_truth_id in retrieved_ids[:k] else 0.0

    @staticmethod
    def precision_at_k(retrieved_ids: List[str], ground_truth_id: str, k: int) -> float:
        """Precision@K for a single-relevant-doc scenario: 1/K if ID is in top K, else 0.0."""
        if ground_truth_id in retrieved_ids[:k]:
            return 1.0 / k
        return 0.0

    @staticmethod
    def reciprocal_rank(retrieved_ids: List[str], ground_truth_id: str) -> float:
        """Reciprocal Rank: 1/rank if found, else 0.0."""
        try:
            rank = retrieved_ids.index(ground_truth_id) + 1
            return 1.0 / rank
        except ValueError:
            return 0.0

    @staticmethod
    def accuracy_qa(context: str, answer_keywords: List[str]) -> float:
        """Simple keyword-based QA accuracy: % of keywords found in context."""
        if not answer_keywords:
            return 1.0
        found = sum(1 for kw in answer_keywords if kw.lower() in context.lower())
        return found / len(answer_keywords)

class EvaluationReport:
    """Aggregates multiple evaluation points into a final report."""
    def __init__(self, mode_name: str):
        self.mode_name = mode_name
        self.points = []

    def add_point(self, metrics: Dict[str, float]):
        self.points.append(metrics)

    def summarize(self) -> Dict[str, float]:
        if not self.points:
            return {}
        summary = {}
        for key in self.points[0].keys():
            summary[key] = np.mean([p[key] for p in self.points])
        return summary
