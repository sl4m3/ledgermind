import logging
from typing import Dict, Type, Any
from .algorithms import DuplicateSearchAlgorithm, RRFJaccardAlgorithm, VectorEmbeddingAlgorithm

logger = logging.getLogger("ledgermind.core.merging.factory")

class AlgorithmFactory:
    """Factory for creating duplicate search algorithms."""
    
    _registry: Dict[str, Type[DuplicateSearchAlgorithm]] = {
        "rrf_jaccard": RRFJaccardAlgorithm,
        "vector_embedding": VectorEmbeddingAlgorithm
    }

    @classmethod
    def register(cls, name: str, algorithm_class: Type[DuplicateSearchAlgorithm]):
        cls._registry[name] = algorithm_class
        logger.debug(f"Algorithm registered: {name}")

    @classmethod
    def create(cls, name: str, **kwargs) -> DuplicateSearchAlgorithm:
        alg_class = cls._registry.get(name)
        if not alg_class:
            logger.warning(f"Algorithm '{name}' not found. Using rrf_jaccard by default.")
            alg_class = RRFJaccardAlgorithm
        return alg_class(**kwargs)
