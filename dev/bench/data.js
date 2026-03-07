window.BENCHMARK_DATA = {
  "lastUpdate": 1772898615313,
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
          "id": "7585098fd5b66ee39ed9b36f9ad39ccc8c413886",
          "message": "refactor: stabilize test execution infrastructure\n\n- Modified Makefile to run tests sequentially by default (-n0) to prevent OOM/resource crashes.\n- Added 'test-parallel' target to Makefile for optional concurrent execution.\n- Updated run_tests.sh to use -n0 for consistency with Makefile.\n- Fixed Makefile indentation (tabs instead of spaces).",
          "timestamp": "2026-03-07T18:42:54+03:00",
          "tree_id": "8e1bf40f19c5ca52b60225ee802b4eceafccec7b",
          "url": "https://github.com/sl4m3/ledgermind/commit/7585098fd5b66ee39ed9b36f9ad39ccc8c413886"
        },
        "date": 1772898325657,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 86.06038023811762,
            "unit": "iter/sec",
            "range": "stddev: 0.000296367435744709",
            "extra": "mean: 11.619748800006846 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 20453.745898080655,
            "unit": "iter/sec",
            "range": "stddev: 0.000008243858515603854",
            "extra": "mean: 48.890800002254764 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 908.8007537955282,
            "unit": "iter/sec",
            "range": "stddev: 0.00011051086441196987",
            "extra": "mean: 1.1003512000002047 msec\nrounds: 5"
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
          "id": "023c7731acfa0216c2ef0f84ce018735dd08b6b1",
          "message": "fix: resolve audit tool test failure and CI cleanup issues\n\n- Updated MockRequest in test_audit_logs_tool to include 'offset' and 'namespace' attributes required by the modern search API.\n- Hardened tearDown cleanup with explicit logger shutdown and a retry loop for directory removal to prevent OSError on GitHub CI.",
          "timestamp": "2026-03-07T18:47:46+03:00",
          "tree_id": "071c2e5d096bb54db2d0333d404ca40e89c543c5",
          "url": "https://github.com/sl4m3/ledgermind/commit/023c7731acfa0216c2ef0f84ce018735dd08b6b1"
        },
        "date": 1772898614311,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 86.46201764195104,
            "unit": "iter/sec",
            "range": "stddev: 0.00024588502532180183",
            "extra": "mean: 11.565772200009405 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 20187.33850120375,
            "unit": "iter/sec",
            "range": "stddev: 0.000007689941187573155",
            "extra": "mean: 49.53600000021652 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 906.3116631808399,
            "unit": "iter/sec",
            "range": "stddev: 0.00010552515143467298",
            "extra": "mean: 1.103373199998714 msec\nrounds: 5"
          }
        ]
      }
    ]
  }
}