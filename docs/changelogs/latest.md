# Latest Release (v3.0.1)

**February 27, 2026**

LedgerMind v3.0.1 introduces significant performance optimizations and stability fixes. This release focuses on making the **Autonomous Knowledge Core** faster and more reliable through incremental validation and enhanced session-based intelligence.

## Major Changes

### Performance Optimization
Drastically reduced recording latency by implementing **Incremental Integrity Validation**.
- **O(1) Checks:** Replaced full repository scans with targeted file-level validation.
- **Embedding Caching:** Pre-computed vectors are now reused during the recording pipeline to eliminate redundant LLM/Embedding calls.

### Enhanced Reflection Intelligence
Refined the **Session-Based Distillation** logic to better capture multi-turn interaction trajectories.
- **Autonomous Turns:** Improved turn boundary detection for autonomous agent tasks.
- **Target Inheritance:** Enhanced the ability to link events to their primary project targets across session gaps.

### System Stability
- **Cache Isolation:** Fixed data leakage in the IntegrityChecker for multi-repository environments.
- **Database Indexing:** Optimized SQLite indexes for faster duplicate detection in episodic memory.
- **Unified Versioning:** Implemented dynamic version loading across core and server modules.

---

**Full Release Notes:** [v3.0.1.md](v3.0.1.md)
**Full changelog:** [v3.0.0...v3.0.1](https://github.com/ledgermind/ledgermind/compare/v3.0.0...v3.0.1)
