window.BENCHMARK_DATA = {
  "lastUpdate": 1772897755698,
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
          "id": "610b8a4b1f1b9d2534df6ecc804990a7629c2abc",
          "message": "chore: sync remaining core and test updates\n\n- Force-added critical audit tests that were previously git-ignored.\n- Synchronized schema and store modifications from I3/I4 integrity phase.\n- Included updates to stress and distillation tests.\n- Reached 100% clean repository state for tracked files.",
          "timestamp": "2026-03-07T18:31:00+03:00",
          "tree_id": "1b7260fd1fdc1f5fa050caeab9e4692721bd2fdf",
          "url": "https://github.com/sl4m3/ledgermind/commit/610b8a4b1f1b9d2534df6ecc804990a7629c2abc"
        },
        "date": 1772897754757,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 86.0383207797448,
            "unit": "iter/sec",
            "range": "stddev: 0.00046326321067477396",
            "extra": "mean: 11.622728000003235 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 18309.652849016747,
            "unit": "iter/sec",
            "range": "stddev: 0.000009737000898634859",
            "extra": "mean: 54.6159999998963 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 902.4277110379454,
            "unit": "iter/sec",
            "range": "stddev: 0.00011377279450127023",
            "extra": "mean: 1.1081219999880432 msec\nrounds: 5"
          }
        ]
      }
    ]
  }
}