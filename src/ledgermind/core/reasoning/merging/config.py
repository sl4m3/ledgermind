from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class MergeConfig:
    """Configuration for MergeEngine."""
    threshold: float = 0.80
    max_candidates: int = 100
    max_workers: int = 4
    timeout: int = 300

    algorithms: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "default": {"name": "vector_embedding"},
        "rrf_jaccard": {"threshold": 0.80},
        "vector_embedding": {
            "threshold": 0.80,
            "keyword_weight": 0.15,
            "use_vector_search": True,
            "vector_search_limit": 100,
            "enable_cache": True,
        }
    })

    def get_algorithm_config(self, algorithm_name: str) -> Dict[str, Any]:
        """Retrieves algorithm-specific configuration."""
        return self.algorithms.get(algorithm_name, {})
