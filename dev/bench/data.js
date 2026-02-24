window.BENCHMARK_DATA = {
  "lastUpdate": 1771894064143,
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
          "id": "85cfc8b85d599ad7ab433b4988f8c98ee8f81a3e",
          "message": "ci: grant contents: write permission to benchmark job to allow gh-pages push",
          "timestamp": "2026-02-24T01:43:27+03:00",
          "tree_id": "b5cbbee6c7159a896d26525fdf82a3df917c1081",
          "url": "https://github.com/sl4m3/ledgermind/commit/85cfc8b85d599ad7ab433b4988f8c98ee8f81a3e"
        },
        "date": 1771886764176,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.08796988953369,
            "unit": "iter/sec",
            "range": "stddev: 0.002028070642715712",
            "extra": "mean: 32.166783600001736 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 243.7837141136391,
            "unit": "iter/sec",
            "range": "stddev: 0.0000993118489467826",
            "extra": "mean: 4.101996737706002 msec\nrounds: 61"
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
          "id": "5201bed9b6bf18e1f8c5636704a8cf77abf5f068",
          "message": "security: protect SSE/WS endpoints, harden Dockerfile, and add GGUF deps",
          "timestamp": "2026-02-24T02:10:06+03:00",
          "tree_id": "612cb66c1184e4380a073197c52c7166c99fa2d4",
          "url": "https://github.com/sl4m3/ledgermind/commit/5201bed9b6bf18e1f8c5636704a8cf77abf5f068"
        },
        "date": 1771888468321,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 27.96824259752373,
            "unit": "iter/sec",
            "range": "stddev: 0.0025762768830507867",
            "extra": "mean: 35.75483859999622 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 241.48972380198796,
            "unit": "iter/sec",
            "range": "stddev: 0.00009536979468797375",
            "extra": "mean: 4.140962953852068 msec\nrounds: 65"
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
          "id": "6ca039cabac0c0119255160244111fca12743308",
          "message": "fix: prevent BackgroundWorker mock crashes in tests",
          "timestamp": "2026-02-24T02:52:26+03:00",
          "tree_id": "3528805d66aef0fb273ab0764d1634fb3fa49a0c",
          "url": "https://github.com/sl4m3/ledgermind/commit/6ca039cabac0c0119255160244111fca12743308"
        },
        "date": 1771891335157,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 32.03122926979307,
            "unit": "iter/sec",
            "range": "stddev: 0.003347203182765632",
            "extra": "mean: 31.219532399995842 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 244.95371849892675,
            "unit": "iter/sec",
            "range": "stddev: 0.00008996017007200249",
            "extra": "mean: 4.082403835826568 msec\nrounds: 67"
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
          "id": "36a8063ec49d7d663f75b1de7d278c1b23bb1396",
          "message": "fix: mock EventSourceResponse to prevent SSE test from hanging in test_auth_disabled_by_default",
          "timestamp": "2026-02-24T03:35:09+03:00",
          "tree_id": "a6281691fed94fc49ae16a401c569f637eb65cc0",
          "url": "https://github.com/sl4m3/ledgermind/commit/36a8063ec49d7d663f75b1de7d278c1b23bb1396"
        },
        "date": 1771893588040,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 30.249171744415413,
            "unit": "iter/sec",
            "range": "stddev: 0.0032982600460632816",
            "extra": "mean: 33.05875639998703 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 245.76015459013854,
            "unit": "iter/sec",
            "range": "stddev: 0.00009433588097852553",
            "extra": "mean: 4.069007857143196 msec\nrounds: 56"
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
          "id": "acd836a3f71e4652e9d6acb7ae8e7ebd6496f0c2",
          "message": "chore: bump version to v2.7.7",
          "timestamp": "2026-02-24T03:43:37+03:00",
          "tree_id": "592b119e9244fcbf4309be18de49471bdb225a1a",
          "url": "https://github.com/sl4m3/ledgermind/commit/acd836a3f71e4652e9d6acb7ae8e7ebd6496f0c2"
        },
        "date": 1771894063900,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.015584885757367,
            "unit": "iter/sec",
            "range": "stddev: 0.004304868595057968",
            "extra": "mean: 34.46423720001803 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 244.46252561670994,
            "unit": "iter/sec",
            "range": "stddev: 0.00009391777325711725",
            "extra": "mean: 4.090606515159256 msec\nrounds: 66"
          }
        ]
      }
    ]
  }
}