window.BENCHMARK_DATA = {
  "lastUpdate": 1771958572808,
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
          "id": "65707e306f48e978c4cae1e736ac5127b622136a",
          "message": "ci: add PyPI publishing workflow",
          "timestamp": "2026-02-24T03:56:44+03:00",
          "tree_id": "9db9a7a7870821ab982ed3f2e23c4bd7bf52b60d",
          "url": "https://github.com/sl4m3/ledgermind/commit/65707e306f48e978c4cae1e736ac5127b622136a"
        },
        "date": 1771894854305,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 34.258125727659994,
            "unit": "iter/sec",
            "range": "stddev: 0.0007436169986810335",
            "extra": "mean: 29.190155000003415 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 242.6263953755048,
            "unit": "iter/sec",
            "range": "stddev: 0.00011953545706289843",
            "extra": "mean: 4.121563107148063 msec\nrounds: 56"
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
          "id": "97c9777f240b42e24ccd9c0bc9a09c9aa0cef4b0",
          "message": "docs: bump version to v2.7.8",
          "timestamp": "2026-02-24T04:03:20+03:00",
          "tree_id": "3b9023614095877ecd655d3845d65e2d79ea85a8",
          "url": "https://github.com/sl4m3/ledgermind/commit/97c9777f240b42e24ccd9c0bc9a09c9aa0cef4b0"
        },
        "date": 1771895252853,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 32.27989822277901,
            "unit": "iter/sec",
            "range": "stddev: 0.0027049599274737296",
            "extra": "mean: 30.979031999993367 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 242.4380314407328,
            "unit": "iter/sec",
            "range": "stddev: 0.00008691694938958002",
            "extra": "mean: 4.124765384611132 msec\nrounds: 65"
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
          "id": "f00b97466919f4339842e6731936a3ec7eaf208b",
          "message": "ci: fix pip install command in publish workflow",
          "timestamp": "2026-02-24T04:05:10+03:00",
          "tree_id": "b2e5dac90263ba734265bac574386d9a5ec300c1",
          "url": "https://github.com/sl4m3/ledgermind/commit/f00b97466919f4339842e6731936a3ec7eaf208b"
        },
        "date": 1771895767574,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 33.75335239986576,
            "unit": "iter/sec",
            "range": "stddev: 0.0005302065114565592",
            "extra": "mean: 29.626686799974777 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 243.17569327788476,
            "unit": "iter/sec",
            "range": "stddev: 0.00010596838187839693",
            "extra": "mean: 4.112253106058867 msec\nrounds: 66"
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
          "id": "6d81e07831f215126c85fc3fcacfbdd19bfadd16",
          "message": "docs: add social banner and comparison table to README",
          "timestamp": "2026-02-24T18:18:22+03:00",
          "tree_id": "02eede82956fe108eb454784d45b452593f86a69",
          "url": "https://github.com/sl4m3/ledgermind/commit/6d81e07831f215126c85fc3fcacfbdd19bfadd16"
        },
        "date": 1771946560184,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 30.492319042760624,
            "unit": "iter/sec",
            "range": "stddev: 0.004612764111030365",
            "extra": "mean: 32.79514420000851 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 244.32669436247627,
            "unit": "iter/sec",
            "range": "stddev: 0.00010021110211028917",
            "extra": "mean: 4.092880651495362 msec\nrounds: 66"
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
          "id": "6d6964771b7e4145b742b51137e3964ef47db6f1",
          "message": "feat: release v2.8.0 with Zero-Touch Automation and Client Hooks",
          "timestamp": "2026-02-24T19:53:06+03:00",
          "tree_id": "1ee26ffe1975445e77f7df1405eb2925c3f70d8b",
          "url": "https://github.com/sl4m3/ledgermind/commit/6d6964771b7e4145b742b51137e3964ef47db6f1"
        },
        "date": 1771952262897,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.96305315841423,
            "unit": "iter/sec",
            "range": "stddev: 0.004484432355431039",
            "extra": "mean: 33.37443599999688 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 243.0996708304002,
            "unit": "iter/sec",
            "range": "stddev: 0.0000927144593040869",
            "extra": "mean: 4.113539095236601 msec\nrounds: 63"
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
          "id": "d0566ee350fffd06f9d9fa6443ca92b966c78804",
          "message": "feat: release v2.8.1 with Zero-Touch Hook documentation and fixes",
          "timestamp": "2026-02-24T20:40:37+03:00",
          "tree_id": "f48021176113d9eacd015e6a18d76b71053aa80d",
          "url": "https://github.com/sl4m3/ledgermind/commit/d0566ee350fffd06f9d9fa6443ca92b966c78804"
        },
        "date": 1771955193852,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.292252755437882,
            "unit": "iter/sec",
            "range": "stddev: 0.0023028595971462625",
            "extra": "mean: 31.956791599998272 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 241.75437976075185,
            "unit": "iter/sec",
            "range": "stddev: 0.00017066302874934165",
            "extra": "mean: 4.136429714281219 msec\nrounds: 63"
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
          "id": "d6365629485ae3323e35c7bc4c5f3e2a3ae47520",
          "message": "feat(bridge): enhance injection policy, automated arbitration and context cleaning",
          "timestamp": "2026-02-24T21:38:58+03:00",
          "tree_id": "69c4cc1a683f9819396eb19429d7145cdb639aac",
          "url": "https://github.com/sl4m3/ledgermind/commit/d6365629485ae3323e35c7bc4c5f3e2a3ae47520"
        },
        "date": 1771958572550,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 32.269773238981195,
            "unit": "iter/sec",
            "range": "stddev: 0.0006159210932149363",
            "extra": "mean: 30.988752000030217 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 241.75527710973125,
            "unit": "iter/sec",
            "range": "stddev: 0.00018898354217235095",
            "extra": "mean: 4.136414360651602 msec\nrounds: 61"
          }
        ]
      }
    ]
  }
}