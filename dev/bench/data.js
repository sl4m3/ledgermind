window.BENCHMARK_DATA = {
  "lastUpdate": 1772376104233,
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
      }
    ]
  }
}