# Latest Release (v3.0.0)

**February 27, 2026**

LedgerMind v3.0.0 transforms the system from a passive memory store into a proactive **Autonomous Knowledge Core**. This release introduces the **DecisionStream Lifecycle Engine**, **Procedural Distillation**, and deep **Zero-Touch Integration** for AI agents.

## Major Changes

### DecisionStream Lifecycle Engine
Replaced the static decision model with an autonomous lifecycle (`PATTERN` → `EMERGENT` → `CANONICAL`). 
- **Temporal Signals:** Added burst protection using reinforcement density and interval stability (variance) analysis.
- **Vitality Decay:** Knowledge is now tracked through `ACTIVE`, `DECAYING`, and `DORMANT` states.

### Procedural Distillation (MemP)
Automatic conversion of successful interaction trajectories into structured `procedural.steps`. This "Memory-to-Procedure" mapping ensures agents have clear instructions for recurring tasks.

### Zero-Touch Hooks Pack
New `ledgermind install` command for transparent memory operations in Gemini CLI, Claude Code, Cursor, and VS Code. Memory is now injected and recorded automatically in the background.

### Security & Integrity
- **Path Traversal:** Implemented absolute path validation and symlink prevention.
- **Transactions:** Hardened SQLite transaction management with `SAVEPOINT` and thread-local isolation.
- **Self-Healing:** Automatic metadata index reconstruction from Markdown source files.

---

**Full Release Notes:** [v3.0.0.md](v3.0.0.md)
**Full changelog:** [v2.8.7...v3.0.0](https://github.com/ledgermind/ledgermind/compare/v2.8.7...v3.0.0)
