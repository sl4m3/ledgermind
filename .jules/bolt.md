
## 2024-05-19 - Eliminate N+1 query in sync_meta_index
**Learning:** We discovered an N+1 query problem during `sync_meta_index` initialization. For every markdown file, `count_links_for_semantic` was being called which executed an individual `SELECT` query against the SQLite database. For larger databases (e.g., 1000 items) this resulted in substantial overhead and slower initialization times.
**Action:** Replaced the N+1 loop by executing a single `count_links_for_semantic_batch` call that fetches all link counts for the target files in chunks before iterating over them. This simple change yields a roughly 100x speedup for this operation.
