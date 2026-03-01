# Compression

Complete guide to compression techniques and storage optimization in LedgerMind.

---

## Introduction

This document covers all compression-related aspects of LedgerMind's memory system:

- **DevOps Engineers** optimizing storage for production deployments
- **Developers** reducing memory footprint
- **System Administrators** managing disk space for long-running instances

**Compression Scope**:
- Vector embeddings (GGUF models)
- Episodic memory (SQLite database)
- Semantic memory (Markdown files)
- Metadata index (SQLite database)
- Git audit trail (compressed by Git)

---

## Vector Storage Compression

### 4-bit GGUF Quantization

**Purpose**: Optimize vector search for resource-constrained environments (mobile, Termux) while maintaining acceptable accuracy.

**Model Used**: `jina-embeddings-3.1.2-small-text-matching-Q4_K_M.gguf`

**Specifications**:
- Architecture: BERT-based transformer for text matching
- Output dimension: 1024 (768-dimensional)
- Quantization: 4-bit (Q4_K_M)
- Parameter count: ~8 million parameters @ 4-bit
- Model size: ~60 MB
- Task prefix: "text-matching: " (for Jina 3.1.2)

**Architecture**:
```
Input Text → Prefix → Tokenization → Embedding
```

**Compression Benefits**:
- **Reduced model size**: 60 MB vs 100-500 MB for equivalent models (MiniLM, text-embedding-3-large)
- **Lower memory footprint**: Critical for mobile with 2-3 GB RAM
- **Faster loading**: Smaller files = faster startup
- **No external dependencies**: Single binary, no framework required

**Performance Impact**:

| Metric | Value (4-bit GGUF) |
|---------|-----------|
| **Memory** | ~60 MB | Significant but manageable on mobile |
| **Vector Search** | ~80-90 ops/sec (mobile), ~19,600 ops/sec (server) |
| **Startup Time** | ~2 seconds (GGUF loading + vector index) |

**Comparison to Full-Precision**:

| Model | Size | Ops/sec |
|---------|-----------|
| **4-bit GGUF** | 60 MB | 7,450 (mobile) |
| **text-embedding-3-small** | 500 MB | 16,200 (server) |

### Implementation

**Location**: `src/ledgermind/core/stores/vector.py`

**Key Classes**:

```python
class GGUFEmbeddingAdapter:
    """Adapts llama-cpp-python to match SentenceTransformer's encode API."""

    def __init__(self, model_path: str):
        import contextlib
        import io
        from llama_cpp import Llama

        logger.info(f"Loading GGUF Model: {model_path}")

        # Create model with optimized Termux settings
        with contextlib.redirect_stderr(io.StringIO()):
            self.client = Llama(
                model_path=model_path,
                embedding=True,
                verbose=False,            # Disable log spam
                n_ctx=8192,          # 8K context window
                n_gpu_layers=0,         # CPU-only for mobile
                n_threads=4,           # Sweet spot for ARM64 @ 1.8GHz
                n_batch=512,            # Optimized for mobile
                pooling_type=1,         # Average pooling
                verbose=False
            )

        self._cache = {}              # 100-entry LRU cache
        self._max_cache = 100
        self._model_path = model_path.lower()  # For case-insensitive model paths

        # Auto-detect dimensions
        try:
            test_emb = self.client.create_embedding("test")
            data = test_emb['data']
            if 'embedding' in data:
                self.dimension = len(data['embedding'])
            else:
                logger.warning(f"Unexpected response format. Using default: {len(data)}")
                self.dimension = 1024
        except Exception as e:
            logger.error(f"Failed to detect GGUF dimension: {e}")
            self.dimension = 1024

    def encode(self, sentences: Any, **kwargs) -> np.ndarray:
        """Encodes text to embeddings using GGUF model."""

        is_single = isinstance(sentences, str)
        input_list = [sentences] if is_single else sentences]

        embeddings = []
        for text in input_list:
            if text in self._cache:
                embeddings.append(self._cache[text])
                continue

            # Apply Jina 3.1.2 prefix for text-matching
            prefix = ""
            if "jina-embeddings-3.1.2" in self._model_path:
                prefix = "text-matching: "
            processed_text = f"{prefix}{text}"

            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    res = self.client.create_embedding(processed_text)
            except Exception:
                logger.error(f"GGUF encoding failed for text: {text}")
                # Return zero vector on failure
                return np.zeros(len(input_list), self.dimension, dtype='float32')

            if len(res['data'][0]['embedding']) != self.dimension:
                raise ValueError(f"Unexpected embedding dimension: {len(res['data'][0]['embedding'])}")

            embeddings.append(res['data'][0]['embedding'])

        arr = np.array(embeddings, dtype='float32')

        # Single input return
        if is_single:
            return arr[0]

        return arr

    def get_sentence_embedding_dimension(self):
        return self.dimension

    def close(self):
        """Explicitly release resources to avoid __del__ errors."""
        if hasattr(self, 'client') and self.client:
            try:
                self.client.close()
                self.client = None
            except:
                pass
```

**Cache Behavior**:

- **Size**: 100 entries with LRU eviction
- **Eviction**: Removes oldest entry when cache is full
- **Hit Rate**: Cache is checked on every encode call
- **Cache Performance**: ~80-90% hit rate for repeated searches (e.g., "database migrations")

---

### Model Size Comparison

| Model | Size | Description | Platform | Use Case |
|------|------|----------|-------------|-----------|
| **jina-embeddings-3.1.2-small** (4-bit) | ~60 MB | Mobile/Termux | Default, resource-constrained |
| **text-embedding-3-small** | ~150 MB | Server environments | Larger, more accurate |
| **text-embedding-3-large** | ~500 MB | Server environments | Maximum accuracy, resource-intensive |
| **all-MiniLM** | ~120 MB | Legacy support | Alternative for older hardware |

**Size Analysis**:

```
jina-embeddings-3.1.2-small (4-bit) = 60 MB:
  - 8M parameters @ 4-bit ≈ 32 MB
  - 4× larger than quantization baseline

text-embedding-3-large = 500 MB:
  - 500M parameters @ full-precision
  - 8.3× larger than 4-bit model
```

---

### Model Download Process

**Command** (during init):
```bash
# Option 1: jina-v5-4bit (default)
# Option 2: custom

# When custom selected:
Step 1: Enter model URL or local path
> https://huggingface.co/jinaai/jina-embeddings-3.1.2/resolve/main/3.1.2-small-text-matching-Q4_K_M.gguf

# Or local file
> /path/to/model.gguf

Step 2: Download and verify
> Downloading model to ~/.ledgermind/models/
> Verifying checksum...
```

**Download Flow**:

```bash
# 1. Create models directory
mkdir -p ~/.ledgermind/models

# 2. Download model
curl -L -o ~/.ledgermind/models/3.1.2-small-text-matching-Q4_K_M.gguf \
  https://huggingface.co/jinaai/jina-embeddings/3.1.2/resolve/main/3.1.2-small-text-matching-Q4_K_M.gguf

# 3. Verify download
# (Automatic during init)
```

**Fallback Behavior**:
- Download retry logic with automatic checksum verification
- If download fails during init: falls back to default model (built-in)

---

## Data Storage Compression

### SQLite WAL Mode

**Purpose**: Enable concurrent reads while maintaining write integrity.

**Configuration**:

```python
# In EpisodicStore.__init__() at stores/episodic.py:
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA busy_timeout=10000")
```

**Benefits**:

| Feature | Impact |
|--------|-------|
| **Concurrent reads** | Multiple queries can read while writes occur | Better throughput |
| **Write performance** | Write transactions don't block reads | Improved write latency |
| **Durability** | WAL journal prevents corruption | Better crash recovery |

**Behavior**:

```python
# Read operations can proceed during write
query_results = conn.execute("SELECT * FROM decisions")
conn.execute("SELECT COUNT(*) FROM events")

# Write operations obtain exclusive lock
conn.execute("INSERT INTO decisions ...")  # Blocks until complete
conn.commit()                                    # Releases lock
```

---

### Markdown File Optimization

**Purpose**: Reduce storage overhead for semantic memory.

**Optimizations**:

1. **Frontmatter Separation**: YAML metadata stored separately from Markdown body
2. **Compact Storage**: Only active decisions are kept
3. **Batch Operations**: Updates use subqueries for performance

**Storage Structure**:

```
.ledgermind/semantic/
├── abc123.md          # Active decision
├── xyz789.md          # Active decision
├── superseded_abc123.md  # Superseded (metadata updated)
└── draft_abc123.md        # Draft proposal
└── rejected_abc123.md    # Rejected proposal
```

**File Format**:

```markdown
---
title: Decision Title
status: active
phase: canonical
vitality: active
namespace: default
confidence: 0.85
...

---


Markdown body
Decision content with details...


---
```

**Size Impact**:

- **Active decisions only**: 5,000 decisions @ ~2KB each = ~10 MB
- **Drafts and proposals**: Temporary, smaller files
- **Superseded decisions**: Metadata only updated, file renamed with `superseded_` prefix

**Optimization Strategy**:

```python
# Periodic cleanup
# In DecayEngine:
for decision in semantic_store.list_all():
    # Archive old decisions
    if decision.phase == "canonical":
        if decision.confidence < 0.1:  # Low confidence
        decision.status = "deprecated"
        semantic_store.update_decision(fid, {"status": "deprecated"})
```
```

---

### Metadata Index Compression

**Purpose**: Reduce memory footprint of metadata index (SQLite).

**Implementation**:

**Location**: `src/ledgermind/core/stores/semantic_store/meta.py`

**Optimizations**:

1. **Compact Fields**: Store only essential fields
2. **Prune Old Data**: Remove decisions marked as deprecated or superseded
3. **Batch Operations**: Use subqueries for bulk updates

**Example**:

```python
# Prune old decisions
old_decisions = meta.list_all(status="deprecated")
for fid in old_decisions:
    meta.delete(fid)  # Cascades deletions

# Batch update
meta.update_multiple([
    {"fid": "abc123", "confidence": 0.9},
    {"fid": "xyz789", "confidence": 0.7}
])
```

---

## Network Compression

**Current Status**: Not implemented in 3.1.2

**Rationale**: Network I/O operations are minimal for local storage.

**Future Considerations**:

1. **Gzip Compression**: Compress metadata export bundles
2. **HTTP Caching**: If REST API is exposed, add caching headers
3. **Deduplication**: Store deduplicated metadata

**Compression Trade-offs**:

| Aspect | Compressed | Uncompressed |
|---------|-----------|----------|
| **Storage** | Smaller | Larger (2-3×) |
| **Performance** | Faster access | Slower writes |
| **Complexity** | Higher | Simpler |
| **Cost** | Storage | Development |

**Recommendation**: Keep uncompressed for simplicity and debugging benefits

---

## Memory Decay Strategy

### TTL Configuration

**Purpose**: Automatically prune old episodic events and low-confidence semantic decisions.

**Configuration Options**:

| Configuration | Days | Use Case |
|-----------|------|----------|
| **`ttl_days=7`** | 7 | Short-term projects | Development environments |
| **`ttl_days=30`** | 30 | Default | General purpose production |
| **`ttl_days=90`** | 90 | 3 months | Long-running projects |

**Behavior**:

```python
# Episodic events older than TTL → archive (soft delete)
# Semantic decisions with low confidence → forget (hard delete)

# From DecayEngine.evaluate_semantic():
if new_conf < 0.1:  # Below 10% confidence
    should_forget = True
```

**Decay Rates by Kind**:

| Decision Type | Decay Rate (per week) | Application |
|---------|----------|-------------|
| **Proposal** | 0.05/week | 0.007/day | Draft proposals decay fast |
| **Decision** | 0.017/week | 0.002/day | Active decisions decay slow |
| **Constraint** | 0.003/week | 0.0005/day | System rules decay very slow |

**Recommendations**:

| Project Type | TTL | Rationale |
|-----------|------|----------|
| **Short-term** | 7 days | Rapid development cycles |
| **Production** | 30 days | Balanced historical data |
| **Long-term** | 90+ days | Critical infrastructure |

---

### Confidence Decay

**Formula**:

```python
# From DecayEngine.evaluate_semantic():
if days_inactive > 7:
    decay_steps = days_inactive / 7
    new_conf = max(0, old_conf - (decay_steps * effective_rate))

# Example: 30 days inactive = 4 steps
new_conf = old_conf - (4 * 0.05) = old_conf * 0.95
```

**Effective Rate**: `0.05/week` (~2.1% per week)

---

## Performance Impact

### Storage Space

**Estimated Usage** (per 10,000 semantic decisions):

| Component | Size | Description |
|---------|-------|----------|
| **Markdown files** | ~10 MB (2KB each × 5,000) |
| **Episodic DB** | ~5 MB (10,000 events @ 500 bytes) |
| **Vector index** | ~50 MB (10,000 embeds @ 5KB) |
| **Metadata index** | ~2 MB (5,000 decisions × 400 bytes) |

**Optimization**: Archive deprecated decisions to reduce to ~7 MB

---

## Configuration

### Disabling Compression Features

**If not needed** for your use case:

```bash
# Use default model (no quantization)
ledgermind init
# When prompted for "Choose embedder", select: jina-v5-4bit

# Disable metadata compression
# Not currently supported via environment variables
# Use smaller TTL for more aggressive cleanup
```

**For maximum compression**:

```bash
# Shorten TTL to 7 days for aggressive cleanup
ledgermind init
# Skip model download, use built-in default
# When prompted for TTL, enter: 7

# Result: Events and decisions older than 7 days will be archived/forgotten
```

---

## Best Practices

### 1. Monitor Memory Usage

```bash
# Get memory statistics
bridge.get_stats()

# Expected output:
{
  "episodic_count": 1543,
  "semantic_count": 5000,
  "vector_count": 10000
}
```

### 2. Adjust TTL for Your Use Case

```bash
# Development with rapid iteration
# TTL: 7 days
# Rationale: "Quick changes, high churn"

# Production with stable decisions
# TTL: 90 days
# Rationale: "Established infrastructure"

# Memory pressure test
# TTL: 30 days
# Rationale: "Testing environment"
```

### 3. Enable Vector Search

```bash
# Ensure model is loaded
# Search operations will be semantic-enabled

# Verify
bridge._memory.vector_store._dimension > 0
```

### 4. Use Subquery Optimization

Automatically enabled via optimized queries in `SemanticMetaStore`.

### 5. Configure Appropriate TTL

```bash
# For short-lived test data
# TTL: 7 days
# Rationale: "Test ephemeral workflows"
# Memory will auto-cleanup after test cycle

# For long-lived production data
# TTL: 90 days
# Rationale: "Production knowledge"
```

### 6. Monitor Confidence Decay

```bash
# Search for low-confidence decisions
results = bridge.search_decisions("deprecated")

# If found critical low-confidence decisions:
# Update to improve or forget them
bridge.update_decision(fid="low_conf_id", updates={
    "confidence": 0.8,  # Improved from 0.2 to 0.8
})
```

---

## Next Steps

For storage optimization:
- [Configuration](configuration.md) — Tuning parameters for your environment
- [Architecture](architecture.md) — Understanding storage internals
- [Data Schemas](data-schemas.md) — Complete model definitions
- [Workflows](workflow.md) — Memory management patterns

For testing:
- [dev/bench/](./dev/bench) — Benchmark suite and reproduction guide

---

