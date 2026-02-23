window.BENCHMARK_DATA = {
  "lastUpdate": 1771886764602,
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
      }
    ]
  }
}