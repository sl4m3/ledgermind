"""
Module for duplicate search and knowledge merging.

Classes:
- MergeEngineFacade: Main interface for the merge engine.
- DuplicateSearchAlgorithm: Search strategy for duplicates.
- TransactionManager: Manage merge transactions.
- DuplicateValidator: Validate candidate and group data.
- MemoryProtocol: Protocol for memory object.
- Result: Wrapper for operation results.
- AlgorithmFactory: Factory for creating algorithms.
- ProposalBuilder: Builder for merge proposals.

Example usage:
```python
from ledgermind.core.reasoning.merging import MergeEngineFacade

engine = MergeEngineFacade(memory)
result = engine.scan_for_duplicates(candidates)
```
"""

from .facade import MergeEngineFacade, MergeEngine
from .config import MergeConfig
from .validator import DuplicateValidator
from .transaction_manager import TransactionManager
from .algorithms import DuplicateSearchAlgorithm, RRFJaccardAlgorithm, BM25Algorithm
from .types import MemoryProtocol, SemanticStoreProtocol, Result
from .algorithm_factory import AlgorithmFactory
from .builder import ProposalBuilder

__all__ = [
    'MergeEngineFacade',
    'MergeEngine',
    'MergeConfig',
    'DuplicateValidator',
    'TransactionManager',
    'DuplicateSearchAlgorithm',
    'RRFJaccardAlgorithm',
    'BM25Algorithm',
    'MemoryProtocol',
    'SemanticStoreProtocol',
    'Result',
    'AlgorithmFactory',
    'ProposalBuilder'
]
