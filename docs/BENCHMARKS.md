# LedgerMind Benchmarking Guide (v2.0)

This guide describes the process for testing the performance and agentic
capabilities of the LedgerMind system according to 2026 standards.

## Overview

LedgerMind includes a comprehensive benchmarking suite designed to measure
system behavior under various scales and conditions. The suite is divided into
two levels: Level 1 focuses on core performance metrics like latency and
throughput, while Level 2 evaluates advanced agentic features such as conflict
resolution and retrieval accuracy.

## Structure

The benchmarking infrastructure is organized into the following components:

- `benchmarks/latency_bench.py`: Performance tests (Level 1).
- `benchmarks/agentic_bench.py`: Accuracy and reliability tests (Level 2).
- `benchmarks/data_loader.py`: Integration with datasets (LoCoMo, LongMemEval).
- `benchmarks/utils.py`: RAM monitoring and result visualization.
- `benchmarks/results/`: Directory for CSV reports and generated plots (PNG).

## Metrics

We measure the following key performance indicators to ensure system integrity:

- **Latency (p50, p95, p99):** Execution delay for write and search operations.
- **Throughput:** Number of operations completed per second (ops/sec).
- **RAM Usage:** Memory consumption as the knowledge base grows.
- **Token Efficiency:** Heuristic estimation of data volume sent to the LLM.
- **Conflict Resolution Rate:** Percentage of successfully resolved collisions
  during concurrent access.
- **Retrieval Accuracy:** Search precision on real-world datasets (Recall).

## Dataset usage

LedgerMind supports standard datasets to provide realistic performance
evaluations.

### LoCoMo (Long-Context Memory)

1. Download the dataset from the [LoCoMo GitHub
   repository](https://github.com/snap-research/LoCoMo).
2. Place the `data.jsonl` file in `benchmarks/datasets/locomo/`.
3. Run the agentic tests using `python benchmarks/agentic_bench.py`.

### LongMemEval

Place the dataset files in the `benchmarks/datasets/longmemeval/` directory.
The system automatically detects and uses these files during evaluation.

## Running tests

Before running any benchmarks, ensure all dependencies are installed.

### Install dependencies

```bash
pip install -r benchmarks/requirements-bench.txt
```

### Performance test (Scalability)

Execute the latency benchmark script to measure system scaling:

```bash
python benchmarks/latency_bench.py
```

This script automatically generates scaling plots in `benchmarks/results/`.

### Agentic functions test

Execute the agentic benchmark script to evaluate accuracy and conflict handling:

```bash
python benchmarks/agentic_bench.py
```

## Performance targets (2026)

We aim for the following targets to maintain high-quality autonomous operation:

- **1,000 records:** Write < 150ms, Read < 15ms.
- **10,000 records:** Write < 200ms, Read < 25ms.
- **100,000 records:** Throughput of at least 5 ops/sec for write operations.
