# Latest Release (v3.0.2)

**February 28, 2026**

LedgerMind v3.0.2 introduces a refined **Balanced Ranking Model** and formalizes the **Normative Authority** logic for knowledge evolution. This release focuses on ensuring authoritative knowledge is prioritized through sophisticated lifecycle-aware scoring.

## Major Changes

### Balanced Ranking & Scoring
The search engine now employs a more nuanced ranking algorithm that incorporates the **Lifecycle State** of each memory.
- **Kind-Based Weighting:** Authoritative `Decisions` now receive a ~35% boost compared to `Proposals`.
- **Phase Multipliers:** Results are scaled based on their maturity: `CANONICAL` (1.5x), `EMERGENT` (1.2x), and `PATTERN` (1.0x).
- **Vitality Aware:** Decaying and Dormant memories are de-prioritized in favor of active knowledge.

### Formalized Normative Authority
Improved the logic for promoting behavioral patterns (`PATTERN`) and observations (`EMERGENT`) to project rules (`DECISION`).
- **Balanced Model:** Implemented a weighted authority score based on Confidence, Utility (Success Signals), and Removal Cost.
- **Dynamic Thresholds:** Transition thresholds are now sensitive to the current lifecycle phase.

### Lifecycle Stability & Fixes
- **Test Robustness:** Fixed critical stability issues in the lifecycle validation suite (`tests/lg.py`).
- **Injection Precision:** Fine-tuned `IntegrationBridge` relevance thresholds for better context injection.

---

**Full Release Notes:** [v3.0.2.md](v3.0.2.md)
**Full changelog:** [v3.0.1...v3.0.2](https://github.com/ledgermind/ledgermind/compare/v3.0.1...v3.0.2)
