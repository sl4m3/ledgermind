## 2024-05-18 - [N+1 Query Elimination in Truth Resolution]
**Learning:** During semantic decision searches (`search_decisions`), the system iteratively queries SQLite for event link counts (`count_links_for_semantic`) while iterating over aggregated candidate decisions. This causes significant N+1 query bottlenecks on large result sets.
**Action:** When gathering data across related datasets in a loop (like truth record resolution), always aggregate the target IDs first and use a batched query method (`IN (...)`) to retrieve metadata in a single call to the backend store.

## 2025-03-01 - [N+1 Query Elimination in Event Grounding Link Retrieval]
**Learning:** When resolving supersession chains (`Memory.process_event` -> supersede), fetching linked episodic events inside a loop (`episodic.get_linked_event_ids(old_id)`) causes N+1 query bottlenecks for large sets of superseded records.
**Action:** Implemented a new batch method `get_linked_event_ids_batch` to aggregate the query using an `IN (...)` clause. Always fetch associated database relations in a single aggregate query instead of looping.
