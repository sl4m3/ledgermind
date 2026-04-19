## $(date +%Y-%m-%d) - VS Code Concurrent Loading States
**Learning:** Overlapping background operations (like file saves and chat responses) can prematurely clear loading indicators if a simple boolean flag is used for state tracking. This causes screen readers to announce incorrect idle states while work is still ongoing.
**Action:** Always use a reference counter (`busyCount`) instead of a boolean for shared UI loading states that map to concurrent async operations.
## 2026-04-19 - VS Code Persistent Error States
**Learning:** Persistent error states in VS Code status bars should not be implicitly cleared by concurrent async completion handlers. When overlapping background tasks share UI loading indicators, decoupling the error boolean from the loading counter is necessary to ensure screen readers do not incorrectly announce error resolution when background tasks complete.
**Action:** Always decouple persistent error state booleans from async reference counters, and require explicit user interaction (e.g. clicking the status bar) to dismiss the error.
