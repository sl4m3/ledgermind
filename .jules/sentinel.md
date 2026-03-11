## 2025-03-11 - Add input boundaries to API models
**Vulnerability:** API request models (e.g., `SearchRequest`, `RecordRequest`) lacked input boundaries and length limits.
**Learning:** Unbounded input fields in Pydantic models expose endpoints to Denial of Service (DoS) risks and unexpected memory consumption.
**Prevention:** Always enforce strict input boundaries utilizing `pydantic.Field` constraints (e.g., `max_length`, `ge`, `le`) for API request models.
