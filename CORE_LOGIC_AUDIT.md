# LedgerMind Core Logic Audit Report
**Date:** 2026-03-12
**Status:** High Priority Issues Detected

## 1. Executive Summary
The audit of `src/ledgermind/core` has identified several critical logical flaws related to thread safety, data atomicity, and consistency across distributed storage layers (SQLite, Vector Index, and Git).

## 2. Critical Issues (🔴)

### 2.1. Race Condition in Global Integrity Caches
*   **Location:** `src/ledgermind/core/stores/semantic_store/integrity.py`
*   **Description:** `_file_data_cache` and `_state_cache` are global mutable dictionaries accessed without any synchronization primitives (Locks).
*   **Impact:** Concurrent operations (e.g., background maintenance vs. CLI user action) can corrupt these caches or cause stale validation, leading to silent invariant violations (I1-I5).
*   **Recommended Fix:** Use `threading.Lock` to wrap cache access or move to `threading.local` if per-thread isolation is sufficient.

### 2.2. Lack of Atomicity between Semantic and Vector Stores
*   **Location:** `src/ledgermind/core/api/services/decision_command.py`
*   **Description:** The `update_decision` flow commits changes to the Metadata DB and Filesystem first, then calls `self.vector.add_documents` as a separate, non-transactional step.
*   **Impact:** If the process crashes between these two steps, the Vector Index becomes desynchronized. Search results will point to outdated content or fail to find new records.
*   **Recommended Fix:** Wrap vector updates within the same transaction or implement a "Vector Dirty" flag in Metadata to trigger reconciliation on the next load.

### 2.3. Double Superseding Logic Flaw
*   **Location:** `src/ledgermind/core/api/services/event_processing.py`
*   **Description:** When processing a `supersede` intent, the system marks target IDs as `superseded` without checking if they were already superseded by another branch.
*   **Impact:** Breaks Invariant I3 (Reference Integrity). It allows multiple active "truths" for the same lineage, causing branching divergence in what should be a linear knowledge evolution.
*   **Recommended Fix:** Verify that all `target_decision_ids` are currently `active` and have no existing `superseded_by` link before committing the new record.

## 3. Serious Logic Flaws (🟡)

### 3.1. Vector Search Namespace Leakage
*   **Location:** `src/ledgermind/core/api/services/query.py`
*   **Description:** `search()` executes vector similarity globally across all namespaces, then filters results by namespace *after* retrieving the top-K.
*   **Impact:** If other namespaces contain high-similarity documents, they can "clog" the top-K results, causing the filter to return empty or low-quality results for the intended namespace.
*   **Recommended Fix:** Include namespace in the vector metadata or perform pre-filtering within the vector engine.

### 3.2. Missing Recency Factor in Confidence Calculation
*   **Location:** `src/ledgermind/core/reasoning/decay.py`
*   **Description:** `calculate_confidence` relies purely on evidence count, stability, and hit count.
*   **Impact:** A decision with 100 links from a year ago maintains 1.0 confidence indefinitely, even if it hasn't been "hit" recently. This prevents the natural "dormancy" phase of old knowledge.
*   **Recommended Fix:** Incorporate a `last_hit_at` or `timestamp` based decay multiplier into the confidence score.

### 3.3. Robustness of `supersedes` Parsing
*   **Location:** `src/ledgermind/core/stores/semantic_store/integrity.py`
*   **Description:** The logic to handle `supersedes` as a string fails if the string is a malformed JSON or a single ID that looks like a list.
*   **Impact:** Can cause crashes or incorrect cycle detection during initialization.

## 4. Minor Observations (🟢)

*   **RRF Constant Tuning:** `k=60` is too high for small result sets, making the ranking nearly flat for the top 5 results.
*   **Annoy Index Sync:** The approximate index is only rebuilt on `save()`. If the system is stopped before the `unsaved_count` threshold (500), the next session uses a slow brute-force NumPy scan.
*   **Trust Boundary Logic:** The restriction `event.source == "agent" and event.kind == "decision"` in `HUMAN_ONLY` mode might be too narrow; other semantic kinds like `proposal` or `intervention` might also need restriction.

## 5. Next Steps
1.  **Sync Locks:** Implement thread-safe access for all global stores and caches.
2.  **Atomic Wrappers:** Create a unified commit hook that handles both Semantic and Vector updates.
3.  **Validation Update:** Enhance `ConflictEngine` to reject superseding of already-superseded records.
