# Latest Release: v3.3.1

## March 14, 2026

LedgerMind v3.3.1 is a critical performance and stability release with database optimizations, concurrency fixes, and improved reliability.

### Highlights

- **Performance:** SQLite index on `linked_id`, N+1 query elimination, 5500+ OPS search
- **Security:** TOCTOU race condition fix, global thread lock registry
- **Stability:** SQLite DB locked errors resolved, manual write blocking
- **UX:** CLI error surfacing, test stability improvements

### Metrics

- Record Decision: **10.31 OPS** (+4.1% vs v3.3.0)
- Search Fast Path: **4,179 OPS** (stable)
- Tests: **300 passed** (all green)

[View full v3.3.1 changelog](./v3.3.1.md)
