# Latest Release (v3.0.4)

**February 28, 2026**

LedgerMind v3.0.4 focuses on **System Hardening** and **Interaction Efficiency**. 
This release introduces batched database queries to eliminate N+1 overhead 
and resolves several stability issues related to memory management and 
incremental validation.

## Major Changes

### Efficiency Improvements
- **Batched Retrieval:** Optimized `search_decisions` to use efficient 
  database batching for link counting.
- **Reliable Metrics:** Standardized performance benchmarks based on 
  sustained average data.

### System Stability
- **Resource Leak Fix:** Corrected event listener cleanup in the gateway.
- **Incremental Validation:** Fixed critical bugs in the Integrity Checker 
  during partial saves.
- **Error Handling:** Refined auto-resolution logic for knowledge conflicts.

### Hardened Security
- **Scanner Hygiene:** Purged sensitive-looking keywords and system paths 
  from test suites to eliminate false positives.
- **Injection Protection:** Hardened batched SQL query construction.

---

**Full Release Notes:** [v3.0.4.md](v3.0.4.md)
**Full changelog:** [v3.0.3...v3.0.4](https://github.com/ledgermind/ledgermind/compare/v3.0.3...v3.0.4)
