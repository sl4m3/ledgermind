# Latest Release (v2.8.7)

**February 26, 2026**

This patch release addresses critical security vulnerabilities, 
optimizes storage performance, and significantly expands test coverage 
to ensure architectural integrity.

## What's Changed

### Security & Hardening
- **Path Traversal:** Fixed a security vulnerability in `ProjectScanner` 
  that allowed arbitrary directory scanning.
- **File System Safety:** Prevented arbitrary file writes in 
  `MemoryTransferManager.export_to_tar`.
- **Git Security:** Hardened `GitIndexer` by validating that `repo_path` 
  is always within the current working directory.
- **Auth Hardening:** Fixed an insecure default configuration that 
  could lead to unauthorized access in certain environments.

### Performance Optimizations
- **Batch Processing:** Implemented batch metadata fetches in 
  `search_decisions`, reducing database I/O overhead.
- **Transaction Speed:** Optimized `sync_meta_index` using batch 
  transactions for massive re-indexing speedups.
- **Search Logic:** Refactored `keyword_search` fallback to use 
  AND-logic and a more efficient single-loop construction.
- **Vector Search:** Integrated `Annoy` for approximate nearest 
  neighbor (ANN) search to handle large-scale vector indices.
- **Parallelism:** Offloaded blocking search operations to a dedicated 
  thread pool.

### Core Logic & Refactoring
- **Recursive CTE:** Optimized `resolve_to_truth` using recursive 
  Common Table Expressions (CTE) for deep knowledge inheritance.
- **Audit History:** Fixed a critical bug where `GitAuditProvider` 
  failed to record interaction events in the semantic history.
- **Architectural Refinement:** Consolidated tool registration into 
  the `LedgerMindTools` class and refactored `SemanticStore` for 
  better maintainability.

### Test Coverage expansion
- **Unit Testing:** Added 50+ new unit tests covering `ProjectScanner`, 
  `ConflictEngine`, `ResolutionEngine`, `EventEmitter`, and `TargetRegistry`.
- **Contract Validation:** Introduced comprehensive validation tests 
  for API contract models and `schemas.py`.

---

**Full changelog:** [v2.8.6...v2.8.7](https://github.com/ledgermind/ledgermind/compare/v2.8.6...v2.8.7)
