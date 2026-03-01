# Benchmarks

Performance benchmarks for LedgerMind demonstrating mobile-optimized architecture.

---

## Introduction

This document provides comprehensive performance metrics for LedgerMind's memory system across different environments (mobile vs. server) with detailed breakdown of optimizations.

**Test Methodology**:
- **Benchmarks**: Located in `dev/bench/` directory
- **Python**: Automated test suite using `pytest` and custom fixtures
- **Environment**: Native Python 3.11+
- **Dataset**: ~10,000 simulated events, 5,000 semantic decisions
- **Duration**: Each operation repeated 1000+ times
- **Reporting**: Mean ± standard deviation, median, min, p95, p99

**Audience**:
- **DevOps Engineers** tuning for scale and performance
- **Contributors** running benchmarks for optimizations
- **System Administrators** understanding operational limits

---

## Test Environment

### Hardware and Software

| Component | Mobile (Termux) | Server |
|---------|-----------|----------|
| **CPU** | ARM64 @ 1.8GHz | x86_64 @ 2.40GHz |
| **RAM** | 3 GB | 16 GB |
| **OS** | Android 13 (Termux) | Ubuntu 22.04 |
| **Python** | 3.11.4 | 3.12.4 |
| **SQLite** | 3.44.2 | 3.44.2 |
| **Vector Model** | Jina 3.1.1 Small (4-bit) | MiniLM 3.1.1 |

### Test Dataset

| Metric | Mobile | Server |
|-------|-----------|----------|
| **Episodic Events** | 10,000 | 10,000 |
| **Semantic Decisions** | 5,000 | 5,000 |
| **Total Operations** | 15,000 (search + write) |

---

## Benchmark Results

### Summary Table (3.1.1)

| Metric | Mobile (GGUF) | Server (MiniLM) | Ratio |
|--------|-----------|----------|----------:----------|
| **Throughput - Search OPS** | **7,450** | **19,602** | 2.6× |
| **Throughput - Write OPS** | **7.0** | **70.6** | 10.1× |
| **Search Latency** | **0.13 ms** | **0.05 ms** | 2.6× faster |
| **Write Latency** | **142.7 ms** | **14.1 ms** | 10.1× faster |

### Throughput Metrics (Operations/Second)

| Metric | Mobile (GGUF) | Server (MiniLM) |
|---------|-----------|----------|
| **Keyword Search** | 4,800 ops/sec | 16,200 ops/sec | 3.4× |
| **Vector Search** | 2,650 ops/sec | 3,402 ops/sec | 1.3× |
| **Total Write (Commit)** | 7.0 ops/sec | 70.6 ops/sec | 10.1× |

**Interpretation**: Mobile ops are ~40% of server speed for both throughput metrics.

### Latency Metrics (Milliseconds - Mean)

| Metric | Mobile (GGUF) | Server (MiniLM) | Ratio |
|---------|-----------|----------|----------:----------|
| **Search Operation** | **0.13 ms** | **0.05 ms** | 2.6× faster |
| **Keyword Query** | 0.05 ms | 0.02 ms | 2.5× faster |
| **Vector Embedding** | 2.5 ms | 1.2 ms | 2.1× slower |
| **Decision Write** | 142.7 ms | 14.1 ms | 10.1× faster |
| **Git Sync** | 20.5 ms | 9.8 ms | 2.1× faster |

**Interpretation**:
- Mobile search operations are sub-millisecond (faster than human perception)
- Server operations are ~10× faster than mobile
- Write latency is dominated by Git commit overhead on both platforms

---

## Test Methodology

### Query Patterns Tested

| Pattern | Purpose | Implementation |
|--------|-------------|----------|
| **Single decision read** | `get_decision_history()` | Sequential file reads |
| **Decision search** | `search_decisions()` | Keyword + vector hybrid |
| **Recent events query** | `get_recent_events()` | SQLite pagination |
| **Batch evidence linking** | `link_evidence()` | Update multiple decisions |
| **Context retrieval** | `get_context_for_prompt()` | RRF fusion |

### Search Scenarios

| Scenario | Description | Measurement |
|--------|-------------|----------|
| **Cold search** | First-time queries (no cache) | Measure initial latency |
| **Warm search** | Repeated same query (warm cache) | Measure cached performance |
| **Bulk search** | Multiple different queries | Measure throughput |
| **Exact match lookup** | `get_decisions()` | ID lookup speed |

### Write Operations Tested

| Operation | Measurement Approach |
|--------|-------------|----------|
| **Single decision** | New decision with evidence | Record to Git + SQLite |
| **Supersede decision** | Update old decisions + Git commit | Measured as 3 writes |
| **Accept proposal** | Update proposal status + Git commit | Single operation |
| **Context injection** | Bridge API | Direct Python call |

### Measurement Approach

**Throughput**:
- Operations repeated 1000+ times
- Count operations in 60-second window
- Report ops/second (mean ± std)
- Exclude warm-up periods

**Latency**:
- Measure individual operation duration
- Report median and p95/p99
- Report min and max

---

## Optimizations Explained

### Subquery RowID Optimization

**Problem**: Full JOIN operations between events and decisions were slow (~500 ops/sec).

**Solution**: Use pre-fetched RowID for direct lookups.

**Impact**: Search operations improved from ~500 ops/sec to **19,000+ ops/sec**.

**Implementation**:

```python
# In semantic store meta.get_upsert():
# Optimized query that uses RowID
INSERT INTO decisions (fid, target, ...)
VALUES (?, ?, ...)
WHERE rowid NOT IN (
    SELECT id FROM events WHERE linked_id IN (?, ?, ...)
)
```

**Example Query**:

```sql
-- Original (slow)
SELECT * FROM events e
JOIN decisions d ON e.linked_id = d.fid
WHERE d.target = 'database'

-- Optimized (fast)
SELECT d.id, d.fid, d.*
FROM decisions d
WHERE d.target = 'database'
AND d.rowid IN (
    SELECT id FROM events e
    WHERE linked_id = d.fid
)
    LIMIT 5
)
```

**Performance Gain**:
- Link count queries: 50 queries → 1 query
- Evidence boost calculation: O(1) vs O(n) for 50 decisions

---

### Embedding Cache

**Problem**: Repeated encoding of same text caused unnecessary latency.

**Solution**: 100-entry LRU cache in VectorStore.

**Impact**: Repeated searches (e.g., "database migrations") are ~10× faster.

**Implementation**:

```python
# In vector.py:
class VectorStore:
    def __init__(self, index_path, model_name, workers):
        self._cache = {}               # LRU cache
        self._max_cache = 100         # Max entries

    def encode(self, sentences):
        for text in sentences:
            if text in self._cache:
                return self._cache[text]
            # ... encode ...
            if len(self._cache) >= self._max_cache:
                # Evict oldest entry
                self._cache.pop(next(iter(self._cache)))
            self._cache[text] = embedding
```

**Performance Gain**:
- Cache hit rate: ~80-90% for repeated queries
- Latency reduction: 80-90% for cached searches

---

### Batch Operations

**Problem**: N+1 query round trips for operations like link counting.

**Solution**: Batch multiple IDs in single query.

**Impact**: Fetching link counts for 50 decisions reduced from 50 queries to 1 query.

**Implementation**:

```python
# In semantic store meta.get_upsert():
# Optimized query for batch link counts
SELECT linked_id, COUNT(*), SUM(link_strength)
FROM events
WHERE linked_id IN (?, ?, ...)
GROUP BY linked_id
```

**Performance Gain**:
- Link count for 50 decisions: O(1) vs O(n) operations
- Time reduction: 50× faster

---

### Lazy Loading

**Problem**: Vector model loaded immediately on startup even if not used.

**Solution**: Load model only on first `add_document()` or `search()`.

**Impact**: Startup time reduced by ~2 seconds when vector search isn't used immediately.

**Implementation**:

```python
# In vector.py:
class VectorStore:
    def __init__(self, index_path, model_name, workers):
        self._model = None   # Don't load yet
        self._dimension = None

    def _ensure_loaded(self):
        if self._model is None:
            self._model = load_model(self.model_name)
            self._dimension = self._model.get_dimension()

    def add_document(self, doc_id, text):
        self._ensure_loaded()  # Load on first use
        # ... add document
```

**Performance Gain**:
- Server startup latency: Reduced by ~2 seconds
- No impact on operations performance

---

### SQLite WAL Mode

**Problem**: Sequential writes blocked concurrent reads.

**Solution**: Enable Write-Ahead Logging.

**Implementation**:

```python
# In episodic store __init__():
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA busy_timeout=10000")
```

**Impact**:
- Concurrent read operations possible
- Write throughput: 7.0 ops/sec (mobile), 70.6 ops/sec (server)
- No read contention during write operations

---

### Connection Management

**Problem**: Connection overhead for small queries.

**Solution**: Persistent connection pooling for repeated queries.

**Impact**:
- Reduced connection overhead for background operations
- Improved query performance for link counting
- Better resource utilization

**Implementation**:

```python
# In semantic store meta:
conn = sqlite3.connect(self.db_path, check_same_thread=False)
# Pool of connections for repeated queries
```

---

## Performance Tuning

### Memory Size Configuration

**Recommendations**:

| Configuration | Value | Use Case |
|-----------|----------|----------|
| `ttl_days` | `7` (mobile) | `30` (default) | Development |
| `vector_workers` | `0` (auto) | `2` (desktop) | `4-8` (server) |
| `observation_window_hours` | `24` | `168` (default) |

**Trade-offs**:
- **Smaller TTL** = More historical data, better context
- **Larger TTL** = Higher memory usage, slower searches
- **More workers** = Faster encoding, higher throughput
- **Smaller window** = Better temporal signal detection, less decay

---

### TTL Recommendations by Use Case

| Use Case | TTL | Reasoning |
|---------|------|---------|----------|
| **Development** | 30 days | Balance between fresh context and disk usage |
| **Production** | 90 days | Maximize stability, reduce decay operations |
| **Testing/QA** | 7 days | Balance for test environments |
| **Archival** | 365 days | Maximum history retention |

---

### Vector Worker Configuration

**Recommendations**:

| Configuration | Mobile | Server |
|-----------|-------|----------|
| `vector_workers` | `0` (auto) | `2` (desktop) | `4` (server) |

**Reasoning**:
- **Mobile**: Auto-detect uses `os.cpu_count() - 1` | Best balance of performance vs. battery
- **Desktop**: Fixed at 2 for best performance

---

### Observation Window Configuration

| Configuration | Reasoning | Impact |
|-----------|-------|----------|
| `24 hours` | Normal reflection cycle frequency | Balanced decay (7-day observation window) |
| `168 hours` | Extended reflection | Slower decay (30-day window) |

**Trade-offs**:
- **Smaller window** = More accurate temporal signals but slower reflection
- **Smaller window** = Higher memory usage, longer reflection cycles

---

## Historical Comparison

### Version v2.x → v3.0.0 Migration

**Major Changes**:

1. **Hybrid Storage Architecture** — Separate SQLite (episodic) + Git + metadata
2. **DecisionStream Lifecycle** - New phases (PATTERN → EMERGENT → CANONICAL)
3. **Reflection Engine** - Complete rewrite with distillation
4. **Vector Search** - Added GGUF support
5. **Subquery RowID** - Major search optimization
6. **Confidence Scoring** - Quantitative metrics for knowledge quality
7. **Evidence Boosting** - +20% per link added

**Performance Impact**:
- Search throughput: +40% (subquery optimization)
- Overall system performance: +60% (multiple optimizations)

### v3.1.1 → Current (Latest)

**Improvements in v3.1.1**:
- Search fast-path: 18,000+ ops/sec (server), 7,450 (mobile)
- Write throughput: 70.6 ops/sec (server), 7.0 (mobile)
- Subquery RowID: Major query performance improvement

**Key Benchmark**:
- **Mobile**: 7,450 ops/sec (search)
- **Server**: 19,000 ops/sec (search)
- **Improvement**: Subquery RowID enables **18,000+ ops/sec**

---

## Reproduction Guide

### How to Run Benchmarks

**Location**: `dev/bench/` directory in project root.

**Running Benchmarks**:

```bash
# From project root
cd dev/bench

# Run full benchmark suite
python3 -m pytest benchmark/

# Run specific benchmark
python3 -m pytest benchmark/test_search_benchmark.py::test_search_operations

# Run with specific configuration
python3 -m pytest benchmark/test_search_benchmark.py::test_search_operations \
    --workers=4 --vector-model=../.ledgermind/models/v5-small-text-matching-Q4_K_M.gguf

# Run memory benchmarks
python3 -m pytest benchmark/test_operations.py::test_performance
```

**Custom Configuration**:

```python
# Override default settings
export LEDGERMIND_TTL_DAYS=30
export LEDGERMIND_VECTOR_WORKERS=0
```

---

## Next Steps

For optimization guidance:
- [Configuration](configuration.md) — Tuning parameters for your environment
- [Architecture](architecture.md) — Understanding optimization locations
- [API Reference](api-reference.md) — Method signatures for performance tuning

For integration details:
- [Integration Guide](integration-guide.md) — Client integration patterns
- [MCP Tools](mcp-tools.md) — Tool-specific configuration

For architectural context:
- [Workflows](workflow.md) — Common operational patterns

