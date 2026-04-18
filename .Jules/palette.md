## $(date +%Y-%m-%d) - VS Code Concurrent Loading States
**Learning:** Overlapping background operations (like file saves and chat responses) can prematurely clear loading indicators if a simple boolean flag is used for state tracking. This causes screen readers to announce incorrect idle states while work is still ongoing.
**Action:** Always use a reference counter (`busyCount`) instead of a boolean for shared UI loading states that map to concurrent async operations.
