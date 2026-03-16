## 2024-03-16 - [Optimize hierarchical ID resolution]
**Learning:** Two-pass list comprehensions for resolving hierarchical IDs (like superseded_by chains) create redundant intermediate allocations and duplicate inputs for subsequent DB calls.
**Action:** Use single-pass set comprehensions (list({ ... })) to concurrently filter, check caches, and deduplicate IDs.
