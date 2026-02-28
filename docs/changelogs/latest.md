# Latest Release (v3.0.3)

**February 28, 2026**

LedgerMind v3.0.3 introduces **Extreme Performance Optimization** and 
fully implements the **Programmatic Normative Ranking** model. This release 
is specifically tuned for speed in resource-constrained environments like 
Android/Termux.

## Major Changes

### Extreme Startup Optimization
We have optimized the startup sequence to eliminate latency during hook 
execution.
- **Lazy Loading:** Machine learning libraries are now loaded only when 
  absolutely required.
- **Instant Core:** Near-zero startup time when using GGUF embedding models.
- **Config Priority:** Database settings now take precedence over defaults 
  for better environment-specific tuning.

### Intelligent Normative Ranking
The search engine core now programmatically applies maturity-based weighting.
- **Decision Boost:** Authoritative rules get a **+35% relevance increase**.
- **Phase Scale:** Results are automatically scaled by maturity: 
  `CANONICAL` (1.5x), `EMERGENT` (1.2x).
- **Consistent Thresholds:** Scores are normalized and clipped to ensure 
  reliable context injection.

### Critical Stability Fixes
- **Vector Engine:** Fixed dimension mismatch and `AxisError` bugs.
- **Robust Mocks:** Improved search logic resilience for testing environments.
- **Refined Tests:** Comprehensive updates to validate lazy loading and 
  ranking accuracy.

---

**Full Release Notes:** [v3.0.3.md](v3.0.3.md)
**Full changelog:** [v3.0.2...v3.0.3](https://github.com/ledgermind/ledgermind/compare/v3.0.2...v3.0.3)
