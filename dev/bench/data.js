window.BENCHMARK_DATA = {
  "lastUpdate": 1772376272216,
  "repoUrl": "https://github.com/sl4m3/ledgermind",
  "entries": {
    "Benchmark": [
      {
        "commit": {
          "author": {
            "email": "staszotov555@gmail.com",
            "name": "sl4m3",
            "username": "sl4m3"
          },
          "committer": {
            "email": "staszotov555@gmail.com",
            "name": "sl4m3",
            "username": "sl4m3"
          },
          "distinct": true,
          "id": "43c566e20765c3fabf0cce0922c49bde7dc6ee91",
          "message": "docs: update README activity and refine project metadata",
          "timestamp": "2026-03-01T05:44:27+03:00",
          "tree_id": "310ae8b018566efde9a44062770035995eb03411",
          "url": "https://github.com/sl4m3/ledgermind/commit/43c566e20765c3fabf0cce0922c49bde7dc6ee91"
        },
        "date": 1772333205256,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 70.52043147560006,
            "unit": "iter/sec",
            "range": "stddev: 0.00041124107046086085",
            "extra": "mean: 14.180287599998564 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 19652.156823555233,
            "unit": "iter/sec",
            "range": "stddev: 0.00000825726853327956",
            "extra": "mean: 50.885000001699154 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 604.2142737147051,
            "unit": "iter/sec",
            "range": "stddev: 0.00011513032234489035",
            "extra": "mean: 1.6550420000044141 msec\nrounds: 5"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "staszotov555@gmail.com",
            "name": "sl4m3",
            "username": "sl4m3"
          },
          "committer": {
            "email": "staszotov555@gmail.com",
            "name": "sl4m3",
            "username": "sl4m3"
          },
          "distinct": true,
          "id": "577b97dea7588dc5e09af1ea64dcfc1f610e6775",
          "message": "docs: refactor documentation filenames to lowercase and update README structure\n\n- Renamed documentation files from uppercase to lowercase for consistency (e.g., ARCHITECTURE.md -> architecture.md).\n- Restructured README.md with clearer sections on 'What is LedgerMind' and core capabilities.\n- Updated .gitignore to include .jules/ and audit/ directories.\n- Refined tutorials and reference materials.",
          "timestamp": "2026-03-01T17:39:25+03:00",
          "tree_id": "5ca07b96711f320450914cc2d640943c4de19a04",
          "url": "https://github.com/sl4m3/ledgermind/commit/577b97dea7588dc5e09af1ea64dcfc1f610e6775"
        },
        "date": 1772376103215,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 69.00863097844604,
            "unit": "iter/sec",
            "range": "stddev: 0.0004043838834699617",
            "extra": "mean: 14.490941000008206 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 19155.91381191575,
            "unit": "iter/sec",
            "range": "stddev: 0.000008348954403226818",
            "extra": "mean: 52.203200004896644 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 607.3210364504671,
            "unit": "iter/sec",
            "range": "stddev: 0.00012396218433302248",
            "extra": "mean: 1.6465756000229703 msec\nrounds: 5"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "73834887+sl4m3@users.noreply.github.com",
            "name": "Stanislav",
            "username": "sl4m3"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "5f5c1d4f84d60213c21c5f9f7dc8ccbf0720609f",
          "message": "🛡️ Sentinel: [MEDIUM] Fix API Key Timing Attack Vulnerability (#41)\n\n* Fix API key timing attack vulnerability in gateway.py and server.py\n\nReplaced standard string equality operators with `hmac.compare_digest`\nfor comparing API keys to prevent timing attacks. Handled optional API\nkey configurations gracefully to prevent regressions. Added sentinel\njournal entry.\n\n* Fix CI test failure in test_multi_process_locking\n\nIncreased `sqlite3` connection timeout to 60.0s and `PRAGMA busy_timeout` to\n60000ms in `SemanticMetaStore` to prevent \"database is locked\" OperationalErrors\nduring highly concurrent multi-process tests in CI pipelines.",
          "timestamp": "2026-03-01T17:42:18+03:00",
          "tree_id": "810fbdac71c5ce9a605784e10f2bda431269cf55",
          "url": "https://github.com/sl4m3/ledgermind/commit/5f5c1d4f84d60213c21c5f9f7dc8ccbf0720609f"
        },
        "date": 1772376268834,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 71.16315725087168,
            "unit": "iter/sec",
            "range": "stddev: 0.0002664506168400499",
            "extra": "mean: 14.052215199990314 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 18461.28852297597,
            "unit": "iter/sec",
            "range": "stddev: 0.000010059037673853083",
            "extra": "mean: 54.16740000327991 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 614.9063128856939,
            "unit": "iter/sec",
            "range": "stddev: 0.00009503043982287246",
            "extra": "mean: 1.6262639999695239 msec\nrounds: 5"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "73834887+sl4m3@users.noreply.github.com",
            "name": "Stanislav",
            "username": "sl4m3"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "58e7de0c107f23980f8e75dad369c76fd3431772",
          "message": "⚡ Bolt: Eliminate N+1 query in grounding link retrieval (#40)\n\nOptimized `Memory.process_event` by replacing individual looped queries\nto `EpisodicStore.get_linked_event_ids` with a batched query method\n`EpisodicStore.get_linked_event_ids_batch`. The new method chunks inputs\nto avoid SQLite parameter limits, fetching all links for superseded\nitems efficiently.",
          "timestamp": "2026-03-01T17:42:05+03:00",
          "tree_id": "2b410c1d0a27c1bc299fa55e79bf99819b785e46",
          "url": "https://github.com/sl4m3/ledgermind/commit/58e7de0c107f23980f8e75dad369c76fd3431772"
        },
        "date": 1772376271299,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 69.12289720715954,
            "unit": "iter/sec",
            "range": "stddev: 0.00043167179552655187",
            "extra": "mean: 14.466986200000065 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 19594.472789796037,
            "unit": "iter/sec",
            "range": "stddev: 0.000008109303333147838",
            "extra": "mean: 51.03480000343552 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 600.8414423913571,
            "unit": "iter/sec",
            "range": "stddev: 0.0001241947880915225",
            "extra": "mean: 1.6643325999950775 msec\nrounds: 5"
          }
        ]
      }
    ]
  }
}