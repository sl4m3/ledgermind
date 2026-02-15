# Failure Modes and Recovery

The system is designed to "Fail Fast" when an invariant is violated.

## 1. IntegrityViolation (System Halt)
**Cause:** Manual tampering with files, broken Git history, or logical cycles.
**Effect:** `Memory()` constructor will raise an exception and refuse to initialize.
**Recovery:** Use Git to revert manual changes or fix the broken YAML frontmatter.

## 2. ConflictError (Record Blocked)
**Cause:** Attempting to record an `active` decision for a `target` that already has one.
**Effect:** `process_event` returns a `MemoryDecision` with `should_persist=False`.
**Recovery:** Use `supersede_decision` to explicitly replace the old knowledge.

## 3. TransitionError (Update Rejected)
**Cause:** Attempting to change immutable fields (e.g., rationale) of an existing record.
**Effect:** API raises an exception.
**Recovery:** Create a new decision instead of trying to "patch" the past.

## 4. Degraded Mode (Episodic Failure)
**Cause:** SQLite DB corruption or missing file.
**Effect:** System may continue to work with Semantic memory but lose episodic history.
**Recovery:** Restore `episodic.db` from backup.
