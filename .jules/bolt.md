## 2024-05-18 - [N+1 Query Elimination in Truth Resolution]
**Learning:** During semantic decision searches (`search_decisions`), the system iteratively queries SQLite for event link counts (`count_links_for_semantic`) while iterating over aggregated candidate decisions. This causes significant N+1 query bottlenecks on large result sets.
**Action:** When gathering data across related datasets in a loop (like truth record resolution), always aggregate the target IDs first and use a batched query method (`IN (...)`) to retrieve metadata in a single call to the backend store.
