window.BENCHMARK_DATA = {
  "lastUpdate": 1772333206162,
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
      }
    ]
  }
}