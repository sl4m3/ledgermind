window.BENCHMARK_DATA = {
  "lastUpdate": 1772156997474,
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
          "id": "2c2425313fb5d7f9136925ec15f00b1c662751a4",
          "message": "fix(cli): add missing import and support for threshold in bridge-context",
          "timestamp": "2026-02-24T21:49:35+03:00",
          "tree_id": "7b4c759f787fb66e641c0268a3ce37971209cbce",
          "url": "https://github.com/sl4m3/ledgermind/commit/2c2425313fb5d7f9136925ec15f00b1c662751a4"
        },
        "date": 1771959250854,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 33.60619299224888,
            "unit": "iter/sec",
            "range": "stddev: 0.0019733671836645018",
            "extra": "mean: 29.756420200010325 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 246.03765274668893,
            "unit": "iter/sec",
            "range": "stddev: 0.00010324966722026333",
            "extra": "mean: 4.0644185507230555 msec\nrounds: 69"
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
          "id": "978120c8fdde6c955190d7c07c303712af637b8f",
          "message": "Update README",
          "timestamp": "2026-02-24T22:21:14+03:00",
          "tree_id": "cbb1ea7a59c54387660134d51ed2498b80f68126",
          "url": "https://github.com/sl4m3/ledgermind/commit/978120c8fdde6c955190d7c07c303712af637b8f"
        },
        "date": 1771961140270,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.98738940314667,
            "unit": "iter/sec",
            "range": "stddev: 0.003605871322792921",
            "extra": "mean: 33.34735099998625 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 243.8892265990645,
            "unit": "iter/sec",
            "range": "stddev: 0.00007931765120786624",
            "extra": "mean: 4.100222112901791 msec\nrounds: 62"
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
          "id": "559a994c31108e4947ad0207d731c27952be4930",
          "message": "feat: release v2.8.2 with probabilistic reflection and procedural distillation",
          "timestamp": "2026-02-25T00:34:35+03:00",
          "tree_id": "536df0929a1d3f6af04caa24214b6832c0e878a1",
          "url": "https://github.com/sl4m3/ledgermind/commit/559a994c31108e4947ad0207d731c27952be4930"
        },
        "date": 1771969126296,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.22847841953624,
            "unit": "iter/sec",
            "range": "stddev: 0.003417665760929151",
            "extra": "mean: 34.21320760000981 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 241.67021832384782,
            "unit": "iter/sec",
            "range": "stddev: 0.00009775313829590803",
            "extra": "mean: 4.137870222221423 msec\nrounds: 63"
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
          "id": "bb1203d4971cafb6c723844d6fc4230fa07fc093",
          "message": "fix(memory): prevent duplicate events in episodic store with deep context comparison",
          "timestamp": "2026-02-25T00:56:10+03:00",
          "tree_id": "68cd8502dcfb5b1650205b8b777eee6c1708f130",
          "url": "https://github.com/sl4m3/ledgermind/commit/bb1203d4971cafb6c723844d6fc4230fa07fc093"
        },
        "date": 1771970429454,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 28.13859095702615,
            "unit": "iter/sec",
            "range": "stddev: 0.0006859888881660692",
            "extra": "mean: 35.53838219999079 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 244.77344170769027,
            "unit": "iter/sec",
            "range": "stddev: 0.00008286764980511002",
            "extra": "mean: 4.085410545455358 msec\nrounds: 66"
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
          "id": "f49be685037a8fa6315e93a3d3054f9eba357114",
          "message": "feat: optimize Jina v5 retrieval, update thresholds, and harden episodic recording",
          "timestamp": "2026-02-25T05:04:06+03:00",
          "tree_id": "bc6cc7fd79670697578d6664e48fe5f710ca4349",
          "url": "https://github.com/sl4m3/ledgermind/commit/f49be685037a8fa6315e93a3d3054f9eba357114"
        },
        "date": 1771985309251,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.14818266240585,
            "unit": "iter/sec",
            "range": "stddev: 0.0041149858257539485",
            "extra": "mean: 34.30745619999698 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 244.18988705656022,
            "unit": "iter/sec",
            "range": "stddev: 0.00009448976164309294",
            "extra": "mean: 4.095173686567847 msec\nrounds: 67"
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
          "id": "d31898fb4d07e77bc6a14b2b2556f225494b6895",
          "message": "Update README",
          "timestamp": "2026-02-25T05:07:17+03:00",
          "tree_id": "bfc89ddfd9a5c11abe4c590ffae54c9f5aa15019",
          "url": "https://github.com/sl4m3/ledgermind/commit/d31898fb4d07e77bc6a14b2b2556f225494b6895"
        },
        "date": 1771985510669,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 32.166598482037294,
            "unit": "iter/sec",
            "range": "stddev: 0.0005210269302196531",
            "extra": "mean: 31.088148800017734 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 238.42430758892124,
            "unit": "iter/sec",
            "range": "stddev: 0.0000995432505549235",
            "extra": "mean: 4.194203225805936 msec\nrounds: 62"
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
          "id": "c41d17ee3a7db88e0ce58ceb83ce2120b1baa57c",
          "message": "Update README",
          "timestamp": "2026-02-25T05:09:04+03:00",
          "tree_id": "0b953ac84189ee7a4cfdc2ed5418be0c2352feb6",
          "url": "https://github.com/sl4m3/ledgermind/commit/c41d17ee3a7db88e0ce58ceb83ce2120b1baa57c"
        },
        "date": 1771985603363,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.298360404008026,
            "unit": "iter/sec",
            "range": "stddev: 0.0012432569633968214",
            "extra": "mean: 34.131602799971006 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 369.96803176754725,
            "unit": "iter/sec",
            "range": "stddev: 0.00019863159615913524",
            "extra": "mean: 2.7029362380917954 msec\nrounds: 105"
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
          "id": "7a8892e9a77aa69d939fd842461e288fc9e5ba6b",
          "message": "Update README",
          "timestamp": "2026-02-25T05:11:38+03:00",
          "tree_id": "6b5ce2f2e35212f14538b28a67303ddb29906ba2",
          "url": "https://github.com/sl4m3/ledgermind/commit/7a8892e9a77aa69d939fd842461e288fc9e5ba6b"
        },
        "date": 1771985769840,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 30.394548103171818,
            "unit": "iter/sec",
            "range": "stddev: 0.0037552459719945776",
            "extra": "mean: 32.900637199986704 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 246.03441053697753,
            "unit": "iter/sec",
            "range": "stddev: 0.00010502379506793414",
            "extra": "mean: 4.064472111106206 msec\nrounds: 63"
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
          "id": "d082cca3e60d94a3c0ad17bedfc07b419b53312a",
          "message": "Update README",
          "timestamp": "2026-02-25T05:17:02+03:00",
          "tree_id": "8f73012947ca02cf59e55d6a008129fd01e3c656",
          "url": "https://github.com/sl4m3/ledgermind/commit/d082cca3e60d94a3c0ad17bedfc07b419b53312a"
        },
        "date": 1771986075028,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 32.55532678491256,
            "unit": "iter/sec",
            "range": "stddev: 0.0007001233640409595",
            "extra": "mean: 30.716939400019783 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 241.87548686100766,
            "unit": "iter/sec",
            "range": "stddev: 0.000089046475494283",
            "extra": "mean: 4.134358603171077 msec\nrounds: 63"
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
          "id": "48573f484578f7d9f53790c4617f36ed712ac899",
          "message": "Update README",
          "timestamp": "2026-02-25T05:20:27+03:00",
          "tree_id": "37f7b111a0a72734a818bfa3ceabfaea12de4433",
          "url": "https://github.com/sl4m3/ledgermind/commit/48573f484578f7d9f53790c4617f36ed712ac899"
        },
        "date": 1771986296899,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 28.636328637557394,
            "unit": "iter/sec",
            "range": "stddev: 0.0024445967399660275",
            "extra": "mean: 34.920677600007366 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 238.4324433859482,
            "unit": "iter/sec",
            "range": "stddev: 0.00012556761540219664",
            "extra": "mean: 4.194060111112102 msec\nrounds: 54"
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
          "id": "3fe8810ba7f7fda0d6c2fcb39a35bd45d4d2c318",
          "message": "Update README",
          "timestamp": "2026-02-25T05:24:08+03:00",
          "tree_id": "3238e57e13030272aa7f24e2fa3f33afa5e97eec",
          "url": "https://github.com/sl4m3/ledgermind/commit/3fe8810ba7f7fda0d6c2fcb39a35bd45d4d2c318"
        },
        "date": 1771986521196,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 33.33384200776925,
            "unit": "iter/sec",
            "range": "stddev: 0.000925339223996513",
            "extra": "mean: 29.99954219999381 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 245.44841876681855,
            "unit": "iter/sec",
            "range": "stddev: 0.00010036088894573473",
            "extra": "mean: 4.074175767862747 msec\nrounds: 56"
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
          "id": "eda4c67f4d0497a585c3c788f6c7aeacf6cd85e8",
          "message": "Update README",
          "timestamp": "2026-02-25T05:24:58+03:00",
          "tree_id": "fad8dc46df3199451e451cd07dda043e2688229f",
          "url": "https://github.com/sl4m3/ledgermind/commit/eda4c67f4d0497a585c3c788f6c7aeacf6cd85e8"
        },
        "date": 1771986558426,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 28.59532821995464,
            "unit": "iter/sec",
            "range": "stddev: 0.0032203249239495203",
            "extra": "mean: 34.970747399995616 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 241.04084609771382,
            "unit": "iter/sec",
            "range": "stddev: 0.00015515186518153245",
            "extra": "mean: 4.14867445160982 msec\nrounds: 62"
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
          "id": "e2f51633f1a34c8e9607b92d81e8981a783538b0",
          "message": "Update README",
          "timestamp": "2026-02-25T05:29:42+03:00",
          "tree_id": "7786784988c56d0b35450511237e12983cc1a7a7",
          "url": "https://github.com/sl4m3/ledgermind/commit/e2f51633f1a34c8e9607b92d81e8981a783538b0"
        },
        "date": 1771986854435,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.831993432330048,
            "unit": "iter/sec",
            "range": "stddev: 0.003333690426281848",
            "extra": "mean: 33.52105860000165 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 237.76043298543863,
            "unit": "iter/sec",
            "range": "stddev: 0.00010551260293607641",
            "extra": "mean: 4.205914278685906 msec\nrounds: 61"
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
          "id": "ea8cf46611fb9f2ad7a54ab91456e15aac84e69c",
          "message": "Update README",
          "timestamp": "2026-02-25T05:29:00+03:00",
          "tree_id": "0f58454ee3e96e64fa23fc479b6c35ec06caeb2c",
          "url": "https://github.com/sl4m3/ledgermind/commit/ea8cf46611fb9f2ad7a54ab91456e15aac84e69c"
        },
        "date": 1771987062233,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.773813223811775,
            "unit": "iter/sec",
            "range": "stddev: 0.0034201508789934326",
            "extra": "mean: 33.58656120003616 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 242.65339139153048,
            "unit": "iter/sec",
            "range": "stddev: 0.00011272373660298737",
            "extra": "mean: 4.121104569218494 msec\nrounds: 65"
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
          "id": "f0c69ad9b7b9e2d1ee76de06d06e512565df2eb1",
          "message": "Update README",
          "timestamp": "2026-02-25T05:36:05+03:00",
          "tree_id": "0742abd4d19f817f7bff68549f223e7580ba19d7",
          "url": "https://github.com/sl4m3/ledgermind/commit/f0c69ad9b7b9e2d1ee76de06d06e512565df2eb1"
        },
        "date": 1771987228471,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.10205375071564,
            "unit": "iter/sec",
            "range": "stddev: 0.0029171642928800135",
            "extra": "mean: 32.15221760000304 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 248.89272810517542,
            "unit": "iter/sec",
            "range": "stddev: 0.00009903611264647521",
            "extra": "mean: 4.017795166668858 msec\nrounds: 66"
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
          "id": "5129d610912de41ff2e65bad9abc31a96b04e4de",
          "message": "Update README",
          "timestamp": "2026-02-25T05:37:13+03:00",
          "tree_id": "6dab444df6b6288e3076ad800c767447e1e99e16",
          "url": "https://github.com/sl4m3/ledgermind/commit/5129d610912de41ff2e65bad9abc31a96b04e4de"
        },
        "date": 1771987292785,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.394643165930173,
            "unit": "iter/sec",
            "range": "stddev: 0.0029141560718922385",
            "extra": "mean: 31.852567800012817 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 234.99601224614736,
            "unit": "iter/sec",
            "range": "stddev: 0.00009925712094128929",
            "extra": "mean: 4.255391359375693 msec\nrounds: 64"
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
          "id": "311e495f2f98b607a41adbff288f0a1bdf1da6ad",
          "message": "Update features on",
          "timestamp": "2026-02-25T05:46:51+03:00",
          "tree_id": "79af6604412769cddc9e4210076b26848cc1d824",
          "url": "https://github.com/sl4m3/ledgermind/commit/311e495f2f98b607a41adbff288f0a1bdf1da6ad"
        },
        "date": 1771987876701,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.354327015969954,
            "unit": "iter/sec",
            "range": "stddev: 0.0004437232273094744",
            "extra": "mean: 31.893524599990993 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 241.8382198667073,
            "unit": "iter/sec",
            "range": "stddev: 0.00010567582216697235",
            "extra": "mean: 4.134995703124034 msec\nrounds: 64"
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
          "id": "e43526c2405b4d1d44b2b2c5fc8608da5509839a",
          "message": "Update features on",
          "timestamp": "2026-02-25T05:52:39+03:00",
          "tree_id": "79af6604412769cddc9e4210076b26848cc1d824",
          "url": "https://github.com/sl4m3/ledgermind/commit/e43526c2405b4d1d44b2b2c5fc8608da5509839a"
        },
        "date": 1771988413955,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.358825907204295,
            "unit": "iter/sec",
            "range": "stddev: 0.0035787428591834793",
            "extra": "mean: 34.061307599995416 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 242.25787842780662,
            "unit": "iter/sec",
            "range": "stddev: 0.00009338312902868113",
            "extra": "mean: 4.127832731342944 msec\nrounds: 67"
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
          "id": "16f514254a587a8516794f348f4efd0d4a651473",
          "message": "Update README",
          "timestamp": "2026-02-25T06:20:56+03:00",
          "tree_id": "7aa110886ab9f942e5e5ce0fb97aa06ca7bb4862",
          "url": "https://github.com/sl4m3/ledgermind/commit/16f514254a587a8516794f348f4efd0d4a651473"
        },
        "date": 1771989933859,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.243772139845476,
            "unit": "iter/sec",
            "range": "stddev: 0.0026775685877713047",
            "extra": "mean: 32.00637859999915 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 245.48588190175226,
            "unit": "iter/sec",
            "range": "stddev: 0.00009167162367120359",
            "extra": "mean: 4.073554015624481 msec\nrounds: 64"
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
          "id": "4bef75a38822f8f5e686d4c81671193b66890ad0",
          "message": "Update README",
          "timestamp": "2026-02-25T16:07:57+03:00",
          "tree_id": "ff42ba58a412559bc6a32018d0c47677a1e16fb8",
          "url": "https://github.com/sl4m3/ledgermind/commit/4bef75a38822f8f5e686d4c81671193b66890ad0"
        },
        "date": 1772025158595,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 27.71089061555909,
            "unit": "iter/sec",
            "range": "stddev: 0.008775824946252613",
            "extra": "mean: 36.086894999994 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 367.54444334683683,
            "unit": "iter/sec",
            "range": "stddev: 0.0001032998263941315",
            "extra": "mean: 2.72075940230265 msec\nrounds: 87"
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
          "id": "86e8c872d67e0798553d4c18375a363ac9beeb15",
          "message": "chore: bump version to 2.8.3 and fix DB locking in search",
          "timestamp": "2026-02-25T18:22:08+03:00",
          "tree_id": "4861437cdef1db3d21afed3f30de92172bd1420a",
          "url": "https://github.com/sl4m3/ledgermind/commit/86e8c872d67e0798553d4c18375a363ac9beeb15"
        },
        "date": 1772033211272,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 27.501232715265772,
            "unit": "iter/sec",
            "range": "stddev: 0.0010358291832729199",
            "extra": "mean: 36.36200639998606 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 241.2627400720913,
            "unit": "iter/sec",
            "range": "stddev: 0.0005257476130661957",
            "extra": "mean: 4.144858836060602 msec\nrounds: 61"
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
          "id": "2b53ff0a07e5f5535777031af77f04e12a5aab6c",
          "message": "Update README",
          "timestamp": "2026-02-25T19:25:36+03:00",
          "tree_id": "c9f0b46222ffb06280b0722cf7a095223a7dcbc0",
          "url": "https://github.com/sl4m3/ledgermind/commit/2b53ff0a07e5f5535777031af77f04e12a5aab6c"
        },
        "date": 1772037594024,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.03071640237135,
            "unit": "iter/sec",
            "range": "stddev: 0.002836137381470571",
            "extra": "mean: 34.44627359999686 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 235.17457692241945,
            "unit": "iter/sec",
            "range": "stddev: 0.0005077649561397557",
            "extra": "mean: 4.252160301876018 msec\nrounds: 53"
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
          "id": "99769924b0a26c74e8a57cb868c9c9f1e8792ff6",
          "message": "Update README",
          "timestamp": "2026-02-25T19:44:42+03:00",
          "tree_id": "356a15f51478f5dd8f2d9f8f4c733d873b53073a",
          "url": "https://github.com/sl4m3/ledgermind/commit/99769924b0a26c74e8a57cb868c9c9f1e8792ff6"
        },
        "date": 1772038210136,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 27.493873292780176,
            "unit": "iter/sec",
            "range": "stddev: 0.0033473549979853912",
            "extra": "mean: 36.37173959998563 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 207.2753191175313,
            "unit": "iter/sec",
            "range": "stddev: 0.0007127636514386525",
            "extra": "mean: 4.824501075465575 msec\nrounds: 53"
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
          "id": "e1fdaeaf119bc88476b9d67a3914db9546324af4",
          "message": "release: version 2.8.4\n\n- Bump version to 2.8.4 in pyproject.toml and VERSION.\n- Update README with new capabilities: Deep Truth Resolution and Self-Healing Index.\n- Enhance Gemini CLI hooks to support structured event recording and tool call separation.\n- Update Architecture docs with autonomous maintenance and multiprocess safety details.\n- Fix API specification tests for version 2.8.4.",
          "timestamp": "2026-02-26T01:57:44+03:00",
          "tree_id": "8d71408d719245b08c9057ccd8fd29ec7e3c55fd",
          "url": "https://github.com/sl4m3/ledgermind/commit/e1fdaeaf119bc88476b9d67a3914db9546324af4"
        },
        "date": 1772060531423,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 30.08297299096933,
            "unit": "iter/sec",
            "range": "stddev: 0.0012509081786279146",
            "extra": "mean: 33.24139539998896 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 220.15720356577907,
            "unit": "iter/sec",
            "range": "stddev: 0.0004732982987761984",
            "extra": "mean: 4.542208857141564 msec\nrounds: 63"
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
          "id": "3a709d1f99295d023286741af617d33d49edd6eb",
          "message": "release: version 2.8.5\n\n- Bump version to 2.8.5 in pyproject.toml and VERSION.\n- Increase default relevance_threshold to 0.7 for cleaner context injection.\n- Synchronize all documentation (README, ARCHITECTURE, CONFIGURATION, API_REFERENCE) with current project status.\n- Adapt injection logic tests to match the new 0.7 threshold and status-based boosting.\n- Ensure GGUF stability with 4 threads in Termux/Android environments by optimizing subprocess execution order.\n- Update expected mcp_api_version in tests for version 2.8.5.",
          "timestamp": "2026-02-26T04:49:23+03:00",
          "tree_id": "3c3d8c45b382ac8af62d082136fc46e38a490857",
          "url": "https://github.com/sl4m3/ledgermind/commit/3a709d1f99295d023286741af617d33d49edd6eb"
        },
        "date": 1772070830879,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.40376134797365,
            "unit": "iter/sec",
            "range": "stddev: 0.002434967755268809",
            "extra": "mean: 34.009254399995825 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 226.2808736850642,
            "unit": "iter/sec",
            "range": "stddev: 0.00047692599619533565",
            "extra": "mean: 4.419286454549365 msec\nrounds: 66"
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
          "id": "a5f3cb0beba36b3483cf2a23d5f0987b4a82c8cc",
          "message": "fix(hooks): align Gemini CLI hooks with JSON I/O protocol",
          "timestamp": "2026-02-26T05:17:13+03:00",
          "tree_id": "c809acf31ac4de1212283469d27f02939bc7f824",
          "url": "https://github.com/sl4m3/ledgermind/commit/a5f3cb0beba36b3483cf2a23d5f0987b4a82c8cc"
        },
        "date": 1772072480483,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 28.97559037154461,
            "unit": "iter/sec",
            "range": "stddev: 0.003118467411307216",
            "extra": "mean: 34.51180760002899 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 223.25027408799846,
            "unit": "iter/sec",
            "range": "stddev: 0.0005419266884426028",
            "extra": "mean: 4.479277815380556 msec\nrounds: 65"
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
          "id": "2f4a8d526984241de0d1c4eca539996ca93f7386",
          "message": "fix(ci): fix semantic search tests by pre-seeding memory and suppress debug logs",
          "timestamp": "2026-02-26T06:00:21+03:00",
          "tree_id": "cc03267d21d2213894d061e84f2eee4a6206a129",
          "url": "https://github.com/sl4m3/ledgermind/commit/2f4a8d526984241de0d1c4eca539996ca93f7386"
        },
        "date": 1772075113764,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 28.014631840508677,
            "unit": "iter/sec",
            "range": "stddev: 0.0020673635182975026",
            "extra": "mean: 35.69563239999525 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 223.94730542315392,
            "unit": "iter/sec",
            "range": "stddev: 0.0005501222757132618",
            "extra": "mean: 4.465336156246558 msec\nrounds: 64"
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
          "id": "ef1b87d95d714c9d573440b617cc8d56fc58b771",
          "message": "refactor: update documentation, core logic and server components",
          "timestamp": "2026-02-26T06:05:30+03:00",
          "tree_id": "b478de8b4254bc63478bb78117f5eebe0ee9fba8",
          "url": "https://github.com/sl4m3/ledgermind/commit/ef1b87d95d714c9d573440b617cc8d56fc58b771"
        },
        "date": 1772075387360,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 26.830696667365295,
            "unit": "iter/sec",
            "range": "stddev: 0.0030457234294918177",
            "extra": "mean: 37.27074299998776 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 225.1487984285796,
            "unit": "iter/sec",
            "range": "stddev: 0.00044360773687831834",
            "extra": "mean: 4.441507158730026 msec\nrounds: 63"
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
          "id": "36b1cc8982453f6973fcb31a4332f77765cb9210",
          "message": "bump: version 2.8.5 -> 2.8.6\n\n- Enhance IntegrationBridge and Memory API to inject rich context fields (rationale, consequences, targets) directly into agent prompts.\n- Update documentation to reflect Jina v5 model recommendation.\n- Add run_tests.sh to .gitignore.\n- Synchronize versioning across pyproject.toml, VERSION file, and server contracts.",
          "timestamp": "2026-02-26T17:45:46+03:00",
          "tree_id": "77173ea173677cc0906aecd983f775986a84b3f1",
          "url": "https://github.com/sl4m3/ledgermind/commit/36b1cc8982453f6973fcb31a4332f77765cb9210"
        },
        "date": 1772117393366,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.720099373302766,
            "unit": "iter/sec",
            "range": "stddev: 0.0031134264987499587",
            "extra": "mean: 33.64726300001166 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 213.7317847466833,
            "unit": "iter/sec",
            "range": "stddev: 0.0005103285215588002",
            "extra": "mean: 4.678761285717089 msec\nrounds: 63"
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
          "id": "b0128f622f795dcbe0d52a4cdf4cf52acc683d9a",
          "message": "docs: update architecture diagram in README.md to reflect current core components and zero-touch hooks",
          "timestamp": "2026-02-26T17:50:48+03:00",
          "tree_id": "585f26edf225f8bd172c4be65a1b40aa9ae652fe",
          "url": "https://github.com/sl4m3/ledgermind/commit/b0128f622f795dcbe0d52a4cdf4cf52acc683d9a"
        },
        "date": 1772117725194,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.779723494921537,
            "unit": "iter/sec",
            "range": "stddev: 0.0035200859651079845",
            "extra": "mean: 33.57989539998698 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 214.9751217632641,
            "unit": "iter/sec",
            "range": "stddev: 0.0005246761873891944",
            "extra": "mean: 4.65170105172088 msec\nrounds: 58"
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
          "id": "63c555eb956860c34831b8344d5d528cc2ef039b",
          "message": "Add assets",
          "timestamp": "2026-02-26T18:12:57+03:00",
          "tree_id": "145aadf48251f0616a626b70144b10d2bc67d6be",
          "url": "https://github.com/sl4m3/ledgermind/commit/63c555eb956860c34831b8344d5d528cc2ef039b"
        },
        "date": 1772119055722,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.187495544457462,
            "unit": "iter/sec",
            "range": "stddev: 0.0032609013764373328",
            "extra": "mean: 34.261247200083744 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 40.17076431228416,
            "unit": "iter/sec",
            "range": "stddev: 0.146101058609695",
            "extra": "mean: 24.893725999985552 msec\nrounds: 52"
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
          "id": "7927966e516c289bd48662f6e3220e90abc1e363",
          "message": "docs: replace mermaid architecture with core-arc.svg in README.md",
          "timestamp": "2026-02-26T18:12:44+03:00",
          "tree_id": "8c867cf301db11684d0b2efcee11fd808f33f37f",
          "url": "https://github.com/sl4m3/ledgermind/commit/7927966e516c289bd48662f6e3220e90abc1e363"
        },
        "date": 1772119058898,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 24.394792995845236,
            "unit": "iter/sec",
            "range": "stddev: 0.006443384025363352",
            "extra": "mean: 40.99235439998665 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 208.73650576092518,
            "unit": "iter/sec",
            "range": "stddev: 0.0005971776656148863",
            "extra": "mean: 4.79072884905596 msec\nrounds: 53"
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
          "id": "7e6dd8aa32c317d750d495b65793787cba447866",
          "message": "perf: optimize search_decisions by deferring JSON parsing\n\n- Fixes 5x performance regression in benchmarks.\n- Moves json.loads() out of the initial candidate loop to the final result formatting stage.",
          "timestamp": "2026-02-26T18:20:37+03:00",
          "tree_id": "08fa24864b12ca7bf3e9d1c052693e42fe528a82",
          "url": "https://github.com/sl4m3/ledgermind/commit/7e6dd8aa32c317d750d495b65793787cba447866"
        },
        "date": 1772119493536,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 27.82973558489695,
            "unit": "iter/sec",
            "range": "stddev: 0.0031865888819018096",
            "extra": "mean: 35.93278839999812 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 220.16230056542088,
            "unit": "iter/sec",
            "range": "stddev: 0.0005417171702155068",
            "extra": "mean: 4.542103700005859 msec\nrounds: 60"
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
          "id": "26c5a9bd5d52ff23fd7947d449134f0f4e926cc4",
          "message": "Refactor sync_meta_index into helper methods (#1)\n\nThis change breaks down the complex `sync_meta_index` method in `SemanticStore` into four smaller, more focused helper methods:\n- `_get_disk_files`: Retrieves relevant files from the disk.\n- `_get_meta_files`: Retrieves files currently indexed in the metadata store.\n- `_remove_orphans`: Removes metadata entries for files that no longer exist on disk.\n- `_update_meta_for_file`: Handles the logic for updating metadata for a single file.\n\nThis improves readability and maintainability of the code, making the synchronization process easier to understand and test. The behavior remains unchanged.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:09:35+03:00",
          "tree_id": "b8c865918f78f8296f1ce315c5b44eefedfc3aa0",
          "url": "https://github.com/sl4m3/ledgermind/commit/26c5a9bd5d52ff23fd7947d449134f0f4e926cc4"
        },
        "date": 1772126029924,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 30.09965858499661,
            "unit": "iter/sec",
            "range": "stddev: 0.0022203267840983374",
            "extra": "mean: 33.222968199993375 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 225.7974426968412,
            "unit": "iter/sec",
            "range": "stddev: 0.00048522168117205705",
            "extra": "mean: 4.4287481206889225 msec\nrounds: 58"
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
          "id": "657f19e3aa4aa6a63df077bf159dc0b32d576e84",
          "message": "Security Fix: Prevent path traversal in ProjectScanner (#3)\n\nValidated root_path in ProjectScanner.__init__ to ensure it is relative to the current working directory using pathlib.\nAdded regression tests in tests/test_valid_scan.py.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:10:46+03:00",
          "tree_id": "eb62775deabad45a893815bc74acb2a520681ab7",
          "url": "https://github.com/sl4m3/ledgermind/commit/657f19e3aa4aa6a63df077bf159dc0b32d576e84"
        },
        "date": 1772126097475,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 28.754189046841788,
            "unit": "iter/sec",
            "range": "stddev: 0.0019981166151192475",
            "extra": "mean: 34.777541400001155 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 222.38668335198312,
            "unit": "iter/sec",
            "range": "stddev: 0.00042809556402061827",
            "extra": "mean: 4.496672124999712 msec\nrounds: 64"
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
          "id": "fad46a06fcfaaf911501f3ae9da3933898eb8566",
          "message": "Fix arbitrary file write vulnerability in MemoryTransferManager.export_to_tar (#6)\n\nThe `export_to_tar` method previously allowed arbitrary file paths, enabling an attacker to write files to any location on the filesystem. This change restricts the `output_path` argument to be a filename only (no directory components allowed), ensuring that exports are always written to the current working directory.\n\nThis is a breaking change for consumers relying on specifying full paths for exports, but necessary for security.\n\nTests were updated to verify the new restriction and ensure valid exports still work when executed in the correct context.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:12:26+03:00",
          "tree_id": "1f651fb036f76aea771163aa9630884d27c721de",
          "url": "https://github.com/sl4m3/ledgermind/commit/fad46a06fcfaaf911501f3ae9da3933898eb8566"
        },
        "date": 1772126208721,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 28.061643753661254,
            "unit": "iter/sec",
            "range": "stddev: 0.002463148800828315",
            "extra": "mean: 35.63583119999976 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 223.50292535343584,
            "unit": "iter/sec",
            "range": "stddev: 0.00048492239306251596",
            "extra": "mean: 4.4742143684189015 msec\nrounds: 57"
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
          "id": "d11054c5916c109c116bca20d57109bcd828d0ed",
          "message": "Refactor MCPServer to use @measure_and_log decorator (#10)\n\n* Refactor MCPServer to use @measure_and_log decorator\n\nIntroduced a `measure_and_log` decorator in `src/ledgermind/server/server.py` to encapsulate timing, logging, and error handling logic for tool handlers. Applied this decorator to `handle_record_decision`, `handle_supersede_decision`, `handle_search`, and `handle_accept_proposal` to reduce boilerplate and improve maintainability.\n\nAdded `tests/server/test_decorator.py` to verify the decorator logic and ensure no regressions.\n\nCo-authored-by: sl4m3 <73834887+sl4m3@users.noreply.github.com>\n\n* Fix CI failures by exposing background module in server package\n\nThe previous refactor caused CI failures in `tests/test_verify_tools_and_audit.py` and others due to `AttributeError: module 'ledgermind.server' has no attribute 'background'`. This was caused by `unittest.mock.patch` failing to resolve `ledgermind.server.background` because the `__init__.py` did not expose the submodule.\n\nThis commit adds `from . import background` and `from . import server` to `src/ledgermind/server/__init__.py` to ensure submodules are accessible as attributes of the package, resolving the import/mocking issues.\n\nVerified by running the failing tests locally.\n\nCo-authored-by: sl4m3 <73834887+sl4m3@users.noreply.github.com>\n\n* Fix CI: Expose background module but not server in __init__\n\nThe `AttributeError` in tests was caused by `unittest.mock` failing to resolve `ledgermind.server.background`.\nWe fix this by adding `from . import background` to `src/ledgermind/server/__init__.py`.\n\nWe deliberately do NOT export `server` (`MCPServer`) in `__init__.py` to avoid potential circular import issues or complex initialization dependencies that might be confusing the test runner or patcher in the CI environment (which led to `AssertionError` in concurrency tests).\n\nVerified locally with `pytest`.\n\nCo-authored-by: sl4m3 <73834887+sl4m3@users.noreply.github.com>\n\n* Refactor Server Decorator & Fix CI\n\n1. Re-applied `@measure_and_log` decorator refactoring to `src/ledgermind/server/server.py`.\n2. Fixed CI failures by ensuring tests use robust `patch.object` instead of fragile string patching for `BackgroundWorker`.\n3. Removed `sys.modules` pollution in `tests/server/test_decorator.py`.\n4. Fixed `NameError` in `src/ledgermind/core/stores/vector.py` fallback path.\n5. Verified all relevant tests pass locally.\n\nCo-authored-by: sl4m3 <73834887+sl4m3@users.noreply.github.com>\n\n---------\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:13:50+03:00",
          "tree_id": "57af38e9a5c5bda863fb21a2e34349e5c6572134",
          "url": "https://github.com/sl4m3/ledgermind/commit/d11054c5916c109c116bca20d57109bcd828d0ed"
        },
        "date": 1772126277929,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 30.655513340742306,
            "unit": "iter/sec",
            "range": "stddev: 0.0035863810941984646",
            "extra": "mean: 32.620559599990884 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 224.2319114059069,
            "unit": "iter/sec",
            "range": "stddev: 0.00045873718264040353",
            "extra": "mean: 4.459668535714302 msec\nrounds: 56"
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
          "id": "749a4393817fcb36b82a1451709df6c860cccc01",
          "message": "Fix security vulnerability in GitIndexer: Validate repo_path is within CWD (#11)\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:14:06+03:00",
          "tree_id": "3d45208d37fd762e452f558c578ed950b3da57ef",
          "url": "https://github.com/sl4m3/ledgermind/commit/749a4393817fcb36b82a1451709df6c860cccc01"
        },
        "date": 1772126291289,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 30.1389133256809,
            "unit": "iter/sec",
            "range": "stddev: 0.0030628758141795337",
            "extra": "mean: 33.17969660000699 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 220.55412542280806,
            "unit": "iter/sec",
            "range": "stddev: 0.0005215596485569087",
            "extra": "mean: 4.534034437501333 msec\nrounds: 64"
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
          "id": "ee78ad44b75bf51ac826e5090e168e71b199254f",
          "message": "Optimize vector search using Annoy for approximate nearest neighbor search (#13)\n\n- Implemented Annoy index in `VectorStore` to replace O(N) full scan.\n- Added `_build_annoy_index` to build and save the index.\n- Updated `load`, `save`, and `compact` to manage the index lifecycle.\n- Implemented hybrid search strategy: uses Annoy for indexed vectors and brute-force for unindexed tail (newly added documents).\n- Added benchmark script `benchmarks/benchmark_vector_search.py`.\n- Benchmark shows ~57x speedup (13.5ms -> 0.235ms for 20k vectors).\n- Falls back gracefully to brute force if Annoy is not available.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:14:52+03:00",
          "tree_id": "44a04618891b39f5e81894fbc0680f473d9c6771",
          "url": "https://github.com/sl4m3/ledgermind/commit/ee78ad44b75bf51ac826e5090e168e71b199254f"
        },
        "date": 1772126334517,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 25.347099633787263,
            "unit": "iter/sec",
            "range": "stddev: 0.02425394806728066",
            "extra": "mean: 39.45224560000611 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 345.53225978287486,
            "unit": "iter/sec",
            "range": "stddev: 0.0005400985630241916",
            "extra": "mean: 2.894085781247687 msec\nrounds: 96"
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
          "id": "0fc71075110bc05a4348919ae283ba6b17d26c3b",
          "message": "feat(core): Optimize resolve_to_truth using recursive CTE (#14)\n\nReplaced the iterative N+1 query loop in `_resolve_to_truth` with a single recursive CTE query in `SemanticMetaStore`. This reduces the resolution time from ~0.35ms to ~0.075ms (4.6x speedup) for long chains.\n\n- Added `resolve_to_truth` to `SemanticMetaStore` in `src/ledgermind/core/stores/semantic_store/meta.py`.\n- Updated `_resolve_to_truth` in `src/ledgermind/core/api/memory.py` to use the new method.\n- Added regression tests in `tests/test_resolution_edge_cases.py` to verify edge cases (broken links, depth limit, circularity).\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:15:10+03:00",
          "tree_id": "c4018b9e7412a3791fbccf7fa50987f3ccdd9ad5",
          "url": "https://github.com/sl4m3/ledgermind/commit/0fc71075110bc05a4348919ae283ba6b17d26c3b"
        },
        "date": 1772126367544,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.536476962527647,
            "unit": "iter/sec",
            "range": "stddev: 0.0009470859645830719",
            "extra": "mean: 31.7093123999939 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 214.18259014946003,
            "unit": "iter/sec",
            "range": "stddev: 0.0006356410420308794",
            "extra": "mean: 4.6689135624991 msec\nrounds: 64"
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
          "id": "f9d1fa9cbeed42f170e720f217c504412aac3b38",
          "message": "Improve test coverage for Memory.check_environment (#18)\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:16:20+03:00",
          "tree_id": "c6d17d42ce3861c997f07fbef62eec8d08ff8182",
          "url": "https://github.com/sl4m3/ledgermind/commit/f9d1fa9cbeed42f170e720f217c504412aac3b38"
        },
        "date": 1772126472275,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 32.33050905214493,
            "unit": "iter/sec",
            "range": "stddev: 0.0020201964555617057",
            "extra": "mean: 30.930536799996844 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 215.4722844772901,
            "unit": "iter/sec",
            "range": "stddev: 0.0004207008365526782",
            "extra": "mean: 4.640968106064685 msec\nrounds: 66"
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
          "id": "97a0165fa9871174b83dc656502d1d5eb3585c01",
          "message": "feat(tests): add comprehensive tests for TargetRegistry (#16)\n\n- Add `tests/core/test_targets.py` covering:\n  - Normalization (exact, alias, case-insensitive, unknown)\n  - Persistence (save/load, file updates)\n  - Singleton pattern verification\n  - Suggestion logic\n  - File corruption handling\n- Use `tempfile` for isolation and fixture for cache clearing.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:15:43+03:00",
          "tree_id": "07373714dbdcd9245955548d5f5c245f020f49ca",
          "url": "https://github.com/sl4m3/ledgermind/commit/97a0165fa9871174b83dc656502d1d5eb3585c01"
        },
        "date": 1772126475653,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 28.7169892465116,
            "unit": "iter/sec",
            "range": "stddev: 0.0024356736807404715",
            "extra": "mean: 34.82259200001181 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 188.4710966326017,
            "unit": "iter/sec",
            "range": "stddev: 0.0028868943269544987",
            "extra": "mean: 5.305853352938044 msec\nrounds: 51"
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
          "id": "8328de05419c048079bb00de10b1552e93be04cc",
          "message": "feat(tests): add validation test for ResolutionEngine (#19)\n\n- Add comprehensive test suite for `ResolutionEngine.validate_intent` in `tests/core/test_resolution_intent.py`.\n- Cover scenarios: abort, valid subset, exact match, missing conflicts, and empty sets.\n- Ensure correct behavior for intent validation logic.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:16:35+03:00",
          "tree_id": "f21c83540f00ca811a89efe35b094c7d40a17b9c",
          "url": "https://github.com/sl4m3/ledgermind/commit/8328de05419c048079bb00de10b1552e93be04cc"
        },
        "date": 1772126478278,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 27.878370994062948,
            "unit": "iter/sec",
            "range": "stddev: 0.003110408666418824",
            "extra": "mean: 35.870101600016824 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 211.26656393493673,
            "unit": "iter/sec",
            "range": "stddev: 0.0004779276680901805",
            "extra": "mean: 4.733356672132783 msec\nrounds: 61"
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
          "id": "676761f3f0b2b9002ed4733037f67134c0e1b21b",
          "message": "feat(test): add tests for EventEmitter (#20)\n\nAdded a new test file `tests/core/utils/test_events.py` to test the `EventEmitter` class.\n- Tests `subscribe` method for adding callbacks and avoiding duplicates.\n- Tests `emit` method for synchronous and asynchronous callbacks.\n- Tests exception handling in callbacks.\n- Verified with `pytest`.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:16:52+03:00",
          "tree_id": "9923aa540b9f0dca51e3e98f9064ee9963edf43b",
          "url": "https://github.com/sl4m3/ledgermind/commit/676761f3f0b2b9002ed4733037f67134c0e1b21b"
        },
        "date": 1772126538435,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 30.224676401465015,
            "unit": "iter/sec",
            "range": "stddev: 0.002174428976763742",
            "extra": "mean: 33.08554860000186 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 212.84751515093689,
            "unit": "iter/sec",
            "range": "stddev: 0.0004560813754957968",
            "extra": "mean: 4.698199080646389 msec\nrounds: 62"
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
          "id": "7f4ffae4c6bc07e7e73f9c3a8e5311c8d3b131da",
          "message": "feat(tests): add unit tests for ConflictEngine (#21)\n\nAdded a new test file `tests/core/reasoning/test_conflict.py` to cover the `check_for_conflicts` method in `ConflictEngine`.\n\nTesting improvements:\n- Verified conflict detection logic with mocked `meta_store`.\n- Verified namespace handling and isolation.\n- Verified behavior for non-decision events.\n- Added regression tests for error conditions.\n\nThis ensures that the conflict detection logic is robust and changes to it will be caught by tests.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:17:09+03:00",
          "tree_id": "a57783b78498606dcdefd268a85e213dbc7024b9",
          "url": "https://github.com/sl4m3/ledgermind/commit/7f4ffae4c6bc07e7e73f9c3a8e5311c8d3b131da"
        },
        "date": 1772126554840,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.40238557139672,
            "unit": "iter/sec",
            "range": "stddev: 0.0006977645459718808",
            "extra": "mean: 31.844714400006065 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 214.46755141302216,
            "unit": "iter/sec",
            "range": "stddev: 0.0005059319444607812",
            "extra": "mean: 4.662710015624683 msec\nrounds: 64"
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
          "id": "384468ee45630eaa30e70f7309ea216404b640eb",
          "message": "test(core): add tests for DistillationEngine trajectories (#22)\n\n- Added `tests/core/test_distillation.py` covering:\n  - Basic successful trajectory distillation\n  - Pagination with `after_id` (ASC/DESC order handling)\n  - Edge cases (empty window, immediate result)\n  - Failure filtering\n  - Multiple trajectories processing\n  - Window size limits\n\nThis improves test coverage for `DistillationEngine.distill_trajectories` as requested.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:17:31+03:00",
          "tree_id": "f61d7f518fcbe5dbe0e5ebd5fd3e613e255786c4",
          "url": "https://github.com/sl4m3/ledgermind/commit/384468ee45630eaa30e70f7309ea216404b640eb"
        },
        "date": 1772126556455,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.997331317413703,
            "unit": "iter/sec",
            "range": "stddev: 0.003014490164422776",
            "extra": "mean: 33.336298800003306 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 214.6810609601686,
            "unit": "iter/sec",
            "range": "stddev: 0.0004262558875034598",
            "extra": "mean: 4.6580727500016295 msec\nrounds: 64"
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
          "id": "d1cf2ce5be7f52b8a88f6f70646489eed0e58eb8",
          "message": "⚡ Optimize keyword_search fallback: Switch to AND logic and single loop construction. (#23)\n\nChanged the fallback keyword search logic from OR (Union) to AND (Intersection).\nThis aligns the fallback behavior with the primary FTS search logic, fixing an inconsistency where fallback was overly broad.\nAdditionally, this improves performance by allowing the database to short-circuit non-matching rows earlier (fail-fast) and reduces the result set size.\nAlso refactored the query construction loop to be more efficient (single pass).\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:17:53+03:00",
          "tree_id": "468b230f420073c5e9588d347eaa9da6187c9be3",
          "url": "https://github.com/sl4m3/ledgermind/commit/d1cf2ce5be7f52b8a88f6f70646489eed0e58eb8"
        },
        "date": 1772126643365,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.139182055931524,
            "unit": "iter/sec",
            "range": "stddev: 0.002288333886772842",
            "extra": "mean: 34.31805320000194 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 213.44991365739253,
            "unit": "iter/sec",
            "range": "stddev: 0.0005086840931142236",
            "extra": "mean: 4.684939819676364 msec\nrounds: 61"
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
          "id": "255f4c61e8c28fbe05305a05b6302309d5228255",
          "message": "test(core): add comprehensive tests for schemas.py (#24)\n\n- Add `tests/core/test_schemas.py` to verify Pydantic models in `src/ledgermind/core/core/schemas.py`.\n- Cover `MemoryEvent`, `DecisionContent`, and `ProposalContent` validation logic.\n- Ensure correct context polymorphism and field constraints.\n- Verify compatibility with Pydantic V2 error messages.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:18:16+03:00",
          "tree_id": "a63cb5d3fb4f3863f40e4c98f5274c083c47fee3",
          "url": "https://github.com/sl4m3/ledgermind/commit/255f4c61e8c28fbe05305a05b6302309d5228255"
        },
        "date": 1772126655741,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 26.387580358106067,
            "unit": "iter/sec",
            "range": "stddev: 0.003078544728785462",
            "extra": "mean: 37.89661599998908 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 207.30854701824288,
            "unit": "iter/sec",
            "range": "stddev: 0.0005014762724067608",
            "extra": "mean: 4.823727793104455 msec\nrounds: 58"
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
          "id": "590b2117521d4047b1e09dcc2e43b2e77e647108",
          "message": "🧪 add unit tests for API contract validation models (#26)\n\n- Added tests/server/test_contracts.py with comprehensive tests for Pydantic models.\n- Covered RecordDecisionRequest, SupersedeDecisionRequest, SearchDecisionsRequest, and SyncGitHistoryRequest.\n- Included validation for min_length, value ranges, and default values.\n- Verified test logic via code review.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:18:44+03:00",
          "tree_id": "58bbea5dc207aaf6f3aeccaab38fb293765b9e7f",
          "url": "https://github.com/sl4m3/ledgermind/commit/590b2117521d4047b1e09dcc2e43b2e77e647108"
        },
        "date": 1772126726323,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 27.72956176983094,
            "unit": "iter/sec",
            "range": "stddev: 0.003551282206652051",
            "extra": "mean: 36.06259659999296 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 211.83392332416943,
            "unit": "iter/sec",
            "range": "stddev: 0.0005206963963293004",
            "extra": "mean: 4.720679220342343 msec\nrounds: 59"
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
          "id": "390536d59483192beb84a5079489e97dfdf289a3",
          "message": "Refactor installer hook script creation logic (#7)\n\nExtracted `_create_hook_script` helper method in `BaseInstaller` to reduce code duplication in `ClaudeInstaller` and `CursorInstaller`. This method handles writing the script content and setting the correct file permissions (0o700).\n\n- Added `_create_hook_script` to `BaseInstaller` in `src/ledgermind/server/installers.py`\n- Updated `ClaudeInstaller.install` to use the helper\n- Updated `CursorInstaller.install` to use the helper\n- Verified with `tests/server/test_hooks_integration.py`\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:22:03+03:00",
          "tree_id": "d621e0db6957727f6bc79b1136f34e294cca3013",
          "url": "https://github.com/sl4m3/ledgermind/commit/390536d59483192beb84a5079489e97dfdf289a3"
        },
        "date": 1772126829336,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 33.204257978586604,
            "unit": "iter/sec",
            "range": "stddev: 0.0009786548843293585",
            "extra": "mean: 30.116619399984756 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 215.77237826567296,
            "unit": "iter/sec",
            "range": "stddev: 0.0004413584223011655",
            "extra": "mean: 4.63451350000293 msec\nrounds: 66"
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
          "id": "6e9ffee1b448eb98f5b31c91bd2b29e9172ebf56",
          "message": "feat(tests): add comprehensive tests for ProjectScanner (#12)\n\n- Implement `tests/server/test_scanner.py` using `unittest` and `tempfile`.\n- Cover scenarios: basic structure, ignored directories, max depth, file size limit, content truncation, and empty directory.\n- Verify `scan()` method output structure and content.\n- Improve test coverage for `ledgermind.server.tools.scanner`.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:23:28+03:00",
          "tree_id": "8807fcadde031d5c23ffcea063cd1afb4957a951",
          "url": "https://github.com/sl4m3/ledgermind/commit/6e9ffee1b448eb98f5b31c91bd2b29e9172ebf56"
        },
        "date": 1772126895616,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 28.59171022361442,
            "unit": "iter/sec",
            "range": "stddev: 0.002303125525694381",
            "extra": "mean: 34.97517259999654 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 215.60377240935122,
            "unit": "iter/sec",
            "range": "stddev: 0.0005206281990413516",
            "extra": "mean: 4.638137769228697 msec\nrounds: 52"
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
          "id": "4aad11ab6531ac7dd86e20cc12b0a9a997d21736",
          "message": "Fix insecure default configuration (auth bypass) (#9)\n\n* Fix insecure default configuration (auth bypass) in gateway\n\nThis change enforces authentication by default in the API gateway.\n- HTTP endpoints now return 500 (Server Error) if LEDGERMIND_API_KEY is not configured, instead of allowing access.\n- WebSocket endpoints now close with code 1008 (Policy Violation) if LEDGERMIND_API_KEY is not configured.\n- Updated tests to verify secure behavior.\n\nCo-authored-by: sl4m3 <73834887+sl4m3@users.noreply.github.com>\n\n* Fix insecure default configuration and update tests\n\nThis change enforces authentication by default in the API gateway.\n- HTTP endpoints now return 500 (Server Error) if LEDGERMIND_API_KEY is not configured, instead of allowing access.\n- WebSocket endpoints now close with code 1008 (Policy Violation) if LEDGERMIND_API_KEY is not configured.\n- Updated `tests/server/test_security.py` to verify secure behavior.\n- Updated `tests/server/test_gateway.py` to use `unittest.mock.patch.dict` to set `LEDGERMIND_API_KEY` and provide the key in headers for protected endpoints, fixing CI failures.\n\nCo-authored-by: sl4m3 <73834887+sl4m3@users.noreply.github.com>\n\n---------\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:23:10+03:00",
          "tree_id": "234909f68fe086a50dfc79536c953b50d6a3c6ea",
          "url": "https://github.com/sl4m3/ledgermind/commit/4aad11ab6531ac7dd86e20cc12b0a9a997d21736"
        },
        "date": 1772126904588,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.61561202694766,
            "unit": "iter/sec",
            "range": "stddev: 0.0018021417216352881",
            "extra": "mean: 31.629942800020668 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 214.57528797477949,
            "unit": "iter/sec",
            "range": "stddev: 0.0005114576243687807",
            "extra": "mean: 4.660368905656727 msec\nrounds: 53"
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
          "id": "ee2ed111ae9c9e6fd7efc6593896a02e0067f6ce",
          "message": "Offload blocking search_decisions to thread pool (#5)\n\nThis commit optimizes the `/search` endpoint by offloading the synchronous `mem.search_decisions` call to a thread pool using `starlette.concurrency.run_in_threadpool`.\n\nThis prevents the main event loop from blocking during long-running search operations, significantly improving concurrency and responsiveness for other endpoints (e.g., health checks, websocket connections).\n\nMeasured Improvement:\n- Before: Concurrent `/health` request blocked for ~1.88s during a slow search.\n- After: Concurrent `/health` request completed in ~0.06s during the same slow search.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:12:09+03:00",
          "tree_id": "68f6594cd8473e699c0f8316d05368336cd8c9e1",
          "url": "https://github.com/sl4m3/ledgermind/commit/ee2ed111ae9c9e6fd7efc6593896a02e0067f6ce"
        },
        "date": 1772126942443,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 26.870537952347902,
            "unit": "iter/sec",
            "range": "stddev: 0.0028001511814571152",
            "extra": "mean: 37.215481200018985 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 219.7465845136634,
            "unit": "iter/sec",
            "range": "stddev: 0.0005076771252727606",
            "extra": "mean: 4.550696440689488 msec\nrounds: 59"
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
          "id": "44daf3344e54b944e6a6d2831caf6017f5f60890",
          "message": "test(core): add tests for Memory.accept_proposal workflow (#17)\n\nAdded a comprehensive test suite in `tests/core/test_memory_proposal.py` to cover:\n- Successful proposal acceptance and conversion to decision.\n- Proposal acceptance with superseding logic.\n- Error handling for missing proposals, invalid kinds, and invalid statuses.\n\nThis ensures reliability and correct state transitions for the proposal acceptance feature.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:24:26+03:00",
          "tree_id": "b39e383778fcfb51a0205397c5f4674035097b3b",
          "url": "https://github.com/sl4m3/ledgermind/commit/44daf3344e54b944e6a6d2831caf6017f5f60890"
        },
        "date": 1772126986732,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 27.391380657822413,
            "unit": "iter/sec",
            "range": "stddev: 0.0026175680886065837",
            "extra": "mean: 36.507834800011096 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 213.7081332059215,
            "unit": "iter/sec",
            "range": "stddev: 0.000527086562960681",
            "extra": "mean: 4.679279094335804 msec\nrounds: 53"
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
          "id": "76f2e3a3c311512045460384efb1eac24fffb6aa",
          "message": "Refactor _register_tools into LedgerMindTools class (#2)\n\nMoved tool definitions from `_register_tools` method in `server.py` to a new `LedgerMindTools` class in `src/ledgermind/server/tools/definitions.py`.\nMoved Prometheus metrics definitions to `src/ledgermind/server/metrics.py` to avoid circular imports.\nUpdated `_register_tools` to instantiate `LedgerMindTools` and register its methods.\n\nThis change improves code readability and maintainability by separating tool logic from the server class.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:27:06+03:00",
          "tree_id": "47f67da10baa1cb8b3a67f92790496b239e69302",
          "url": "https://github.com/sl4m3/ledgermind/commit/76f2e3a3c311512045460384efb1eac24fffb6aa"
        },
        "date": 1772127073479,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 28.187106713406003,
            "unit": "iter/sec",
            "range": "stddev: 0.0029121055720959252",
            "extra": "mean: 35.477213399997254 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 214.65657655210785,
            "unit": "iter/sec",
            "range": "stddev: 0.0005020863292878855",
            "extra": "mean: 4.658604064512554 msec\nrounds: 62"
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
          "id": "46e2277df93fd7b9af248073ce697834dc34d55b",
          "message": "Refactor SemanticStore to use shared _upsert_metadata method (#8)\n\nThis commit introduces a private helper method `_upsert_metadata` in `SemanticStore` to encapsulate the logic for upserting metadata to the `SemanticMetaStore`. This reduces code duplication between `save` and `update_decision` methods and ensures consistent handling of content caching (appending rationale), keyword formatting, and conflict detection.\n\nChanges:\n- Added `_upsert_metadata` method to `SemanticStore`.\n- Updated `save` method to use `_upsert_metadata`.\n- Updated `update_decision` method to use `_upsert_metadata`.\n- Added `datetime` import to support type hinting.\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:22:52+03:00",
          "tree_id": "261997cec75b530ed60c3f646245990c141e7dc0",
          "url": "https://github.com/sl4m3/ledgermind/commit/46e2277df93fd7b9af248073ce697834dc34d55b"
        },
        "date": 1772127194924,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.47341165207267,
            "unit": "iter/sec",
            "range": "stddev: 0.0035649910956439225",
            "extra": "mean: 31.77285040003426 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 326.8836067974629,
            "unit": "iter/sec",
            "range": "stddev: 0.000368161676460974",
            "extra": "mean: 3.0591928723412547 msec\nrounds: 94"
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
          "id": "94705d9dda2d9e833fb19ca33eefea303c4b62ff",
          "message": "🧹 Refactor imports in SemanticStore to top level (#4)\n\n* Refactor imports in SemanticStore\n\nMoves import statements from inside methods to the top level of the file\nin `src/ledgermind/core/stores/semantic.py`. This improves code readability\nand adheres to PEP 8 style guidelines.\n\n- Moved standard library imports: `subprocess`, `json`, `re`, `datetime`.\n- Moved internal imports: `NoAuditProvider`, `MigrationEngine`, `ConflictError`, `TransactionManager`.\n- Verified no circular import issues were introduced.\n\nCo-authored-by: sl4m3 <73834887+sl4m3@users.noreply.github.com>\n\n* Refactor imports in SemanticStore and fix flaky CI test\n\n- Moved import statements from inside methods to the top level in `src/ledgermind/core/stores/semantic.py` to improve code health and follow PEP 8.\n- Increased write cooldown in `tests/server/test_integration.py` to 1.0s to prevent flaky failures in slow CI environments.\n\nCo-authored-by: sl4m3 <73834887+sl4m3@users.noreply.github.com>\n\n---------\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:31:04+03:00",
          "tree_id": "e269273b11c4e2f8441de0476ba5753777149b39",
          "url": "https://github.com/sl4m3/ledgermind/commit/94705d9dda2d9e833fb19ca33eefea303c4b62ff"
        },
        "date": 1772127309584,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 28.255739305775432,
            "unit": "iter/sec",
            "range": "stddev: 0.00547102766176436",
            "extra": "mean: 35.391039999990426 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 215.32569564892657,
            "unit": "iter/sec",
            "range": "stddev: 0.00044283718810222153",
            "extra": "mean: 4.644127571427564 msec\nrounds: 63"
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
          "id": "cf399d8615f08795652375f39fe8d18c19ac7428",
          "message": "Optimize `sync_meta_index` with batch transaction (#15)\n\n- Add `batch_update` context manager and `rollback_transaction` to `SemanticMetaStore`\n- Wrap `disk_files` loop in `sync_meta_index` with `batch_update` to reduce I/O and commit overhead\n- Conditionally use batch update only if not already in a transaction to avoid nesting errors\n- Measured performance improvement: ~35% speedup (1.33s -> 0.98s for 500 files)\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:33:45+03:00",
          "tree_id": "74847cd250043d179964a1576e6aea4d7df48006",
          "url": "https://github.com/sl4m3/ledgermind/commit/cf399d8615f08795652375f39fe8d18c19ac7428"
        },
        "date": 1772127463827,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 32.83297154244395,
            "unit": "iter/sec",
            "range": "stddev: 0.00048152860112152794",
            "extra": "mean: 30.45718839999836 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 200.4037061748368,
            "unit": "iter/sec",
            "range": "stddev: 0.0024142204259677523",
            "extra": "mean: 4.989927676924183 msec\nrounds: 65"
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
          "id": "ed7bb0f4a9f4f4c1e2bb1d2b99f619a0ffe0b369",
          "message": "feat: Optimize search_decisions by batching metadata fetches (#25)\n\n- Add `get_batch_by_fids` to `MetadataStore` interface and `SemanticMetaStore`.\n- Refactor `_resolve_to_truth` to accept an optional local cache.\n- Optimize `Memory.search_decisions` to pre-fetch metadata for candidates and their superseding documents, reducing N+1 queries to a few batch queries.\n- Verified with benchmarks (slight improvement in local SQLite, significant reduction in query count).\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:38:03+03:00",
          "tree_id": "1bf1875218293947f8b3a02d3ec2168b2faf2cae",
          "url": "https://github.com/sl4m3/ledgermind/commit/ed7bb0f4a9f4f4c1e2bb1d2b99f619a0ffe0b369"
        },
        "date": 1772127733588,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.41634305687511,
            "unit": "iter/sec",
            "range": "stddev: 0.0011517374869820021",
            "extra": "mean: 31.830566599990103 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 230.84234521986446,
            "unit": "iter/sec",
            "range": "stddev: 0.0004810301911126911",
            "extra": "mean: 4.33196084127267 msec\nrounds: 63"
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
          "id": "5d2ddae0c9e93d5b39a6a99c0386b1bad4f981a9",
          "message": "feat: Optimize search_decisions by batching metadata fetches (#25)\n\n- Add `get_batch_by_fids` to `MetadataStore` interface and `SemanticMetaStore`.\n- Refactor `_resolve_to_truth` to accept an optional local cache.\n- Optimize `Memory.search_decisions` to pre-fetch metadata for candidates and their superseding documents, reducing N+1 queries to a few batch queries.\n- Verified with benchmarks (slight improvement in local SQLite, significant reduction in query count).\n\nCo-authored-by: google-labs-jules[bot] <161369871+google-labs-jules[bot]@users.noreply.github.com>",
          "timestamp": "2026-02-26T20:38:03+03:00",
          "tree_id": "1bf1875218293947f8b3a02d3ec2168b2faf2cae",
          "url": "https://github.com/sl4m3/ledgermind/commit/5d2ddae0c9e93d5b39a6a99c0386b1bad4f981a9"
        },
        "date": 1772128691404,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 29.61434459147795,
            "unit": "iter/sec",
            "range": "stddev: 0.003410596313822241",
            "extra": "mean: 33.767419600019366 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 229.61080793710755,
            "unit": "iter/sec",
            "range": "stddev: 0.0005287286948144889",
            "extra": "mean: 4.355195685187035 msec\nrounds: 54"
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
          "id": "a60496bddb4dfc6ef002b7497382dbaa3889fcdb",
          "message": "feat: Optimize search_decisions by batching metadata fetches (#25)\n\n- Add `get_batch_by_fids` to `MetadataStore` interface and `SemanticMetaStore`.\n- Refactor `_resolve_to_truth` to accept an optional local cache.\n- Optimize `Memory.search_decisions` to pre-fetch metadata for candidates and their superseding documents, reducing N+1 queries to a few batch queries.\n- Verified with benchmarks (slight improvement in local SQLite, significant reduction in query count).",
          "timestamp": "2026-02-26T20:38:03+03:00",
          "tree_id": "1bf1875218293947f8b3a02d3ec2168b2faf2cae",
          "url": "https://github.com/sl4m3/ledgermind/commit/a60496bddb4dfc6ef002b7497382dbaa3889fcdb"
        },
        "date": 1772128872543,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 31.327727420303102,
            "unit": "iter/sec",
            "range": "stddev: 0.0012449684545318424",
            "extra": "mean: 31.92060459999766 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 228.03446604137397,
            "unit": "iter/sec",
            "range": "stddev: 0.0005710006232876382",
            "extra": "mean: 4.385301999999258 msec\nrounds: 63"
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
          "id": "a451601977594df79e895d13fe2fd37df61c98b8",
          "message": "test: Fix cleanup in test_valid_scan",
          "timestamp": "2026-02-26T22:20:54+03:00",
          "tree_id": "8dea4ecb64bba2c6e91d6e532f17987e759e850d",
          "url": "https://github.com/sl4m3/ledgermind/commit/a451601977594df79e895d13fe2fd37df61c98b8"
        },
        "date": 1772133896459,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 30.509245622485025,
            "unit": "iter/sec",
            "range": "stddev: 0.0023318260398085895",
            "extra": "mean: 32.7769493999881 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 228.52409594870954,
            "unit": "iter/sec",
            "range": "stddev: 0.0005218716425699236",
            "extra": "mean: 4.375906163630299 msec\nrounds: 55"
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
          "id": "5fbc56553e4bed3db63ee4fd80acb8c971e8e804",
          "message": "chore: bump version to 2.8.7 and finalize changelog",
          "timestamp": "2026-02-26T23:15:51+03:00",
          "tree_id": "0dc45ded9d33a01f02d40e43aece8b1edbed0cd7",
          "url": "https://github.com/sl4m3/ledgermind/commit/5fbc56553e4bed3db63ee4fd80acb8c971e8e804"
        },
        "date": 1772137197537,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 25.259143530856015,
            "unit": "iter/sec",
            "range": "stddev: 0.00311108512055797",
            "extra": "mean: 39.589624199982154 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 231.1334235022629,
            "unit": "iter/sec",
            "range": "stddev: 0.00046903760515695265",
            "extra": "mean: 4.326505378787026 msec\nrounds: 66"
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
          "id": "20c104f0e9e03efd12c70f4f7d5a70b5ce49907c",
          "message": "Fix git",
          "timestamp": "2026-02-27T02:08:25+03:00",
          "tree_id": "d2e5258911b3b41c4475dc9f911c184454226ea0",
          "url": "https://github.com/sl4m3/ledgermind/commit/20c104f0e9e03efd12c70f4f7d5a70b5ce49907c"
        },
        "date": 1772147586387,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 23.033956137558437,
            "unit": "iter/sec",
            "range": "stddev: 0.00265613289533479",
            "extra": "mean: 43.41416620002292 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 229.4311999579385,
            "unit": "iter/sec",
            "range": "stddev: 0.0005327187628982299",
            "extra": "mean: 4.358605107689493 msec\nrounds: 65"
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
          "id": "7cb18a8a8857d4160b9fcb144b12b41a57804840",
          "message": "feat: implement DecisionStream ontology and autonomous lifecycle management\n\n- Unified API to use DecisionStream with lifecycle fields (phase, vitality)\n- Added LifecycleEngine for temporal metrics and phase transitions\n- Refactored memory.py to handle KIND_INTERVENTION and dynamic lifecycle ranking\n- Updated SQL schema in meta.py with indices for phase and vitality\n- Added comprehensive lifecycle and ranking tests\n- Updated documentation to reflect the new ontology",
          "timestamp": "2026-02-27T04:11:18+03:00",
          "tree_id": "f378083361da7c32a9e6a9a8481b39c266254adb",
          "url": "https://github.com/sl4m3/ledgermind/commit/7cb18a8a8857d4160b9fcb144b12b41a57804840"
        },
        "date": 1772154940548,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 22.99611656301755,
            "unit": "iter/sec",
            "range": "stddev: 0.0033769052957866395",
            "extra": "mean: 43.48560319998569 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 218.1194669729022,
            "unit": "iter/sec",
            "range": "stddev: 0.0005082469162342903",
            "extra": "mean: 4.584643516134365 msec\nrounds: 62"
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
          "id": "db518a7f224bd93d00491d08e62c6e0b84e5edcc",
          "message": "fix(core): resolve SQLite transaction race conditions and add Jina v5 auto-download\n\n- Improved transaction management in SemanticMetaStore to handle nested calls and prevent 'no transaction active' errors.\n- Fixed race condition in SemanticStore rollback that prevented correct re-acquisition of locks.\n- Implemented auto-download logic for Jina v5 GGUF embedding model from Hugging Face.\n- Updated environment checks to verify GGUF model availability.\n- Updated lifecycle tests in tests/lg.py to match current SemanticMetaStore schema.",
          "timestamp": "2026-02-27T04:37:09+03:00",
          "tree_id": "866ab36bd955d47b8b91b997bf4b98ef530eb90b",
          "url": "https://github.com/sl4m3/ledgermind/commit/db518a7f224bd93d00491d08e62c6e0b84e5edcc"
        },
        "date": 1772156481995,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 24.617436179498053,
            "unit": "iter/sec",
            "range": "stddev: 0.0015371991202207038",
            "extra": "mean: 40.62161439999272 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 224.04086009956572,
            "unit": "iter/sec",
            "range": "stddev: 0.0004971275126403975",
            "extra": "mean: 4.463471527272263 msec\nrounds: 55"
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
          "id": "84f930342bd91c2d89fe175a96325c06abd739db",
          "message": "chore(security): suppress Bandit B113 for model download stream\n\nUsing timeout=None is intentional for large (~400MB) model downloads to\nensure completion in constrained environments. Added # nosec B113 to\nsatisfy the security scan.",
          "timestamp": "2026-02-27T04:40:36+03:00",
          "tree_id": "0913d92e5aa6e7c45eb9b7f38c8fb4816637c079",
          "url": "https://github.com/sl4m3/ledgermind/commit/84f930342bd91c2d89fe175a96325c06abd739db"
        },
        "date": 1772156692379,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 22.81107605850664,
            "unit": "iter/sec",
            "range": "stddev: 0.0029584229914009328",
            "extra": "mean: 43.838352799980385 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 209.42249984463564,
            "unit": "iter/sec",
            "range": "stddev: 0.0004460538896122483",
            "extra": "mean: 4.775036114753049 msec\nrounds: 61"
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
          "id": "12abfe6c05da7a2e08dc3df2befa57f46ac8c6fb",
          "message": "fix(core): make check_environment robust to missing config in tests",
          "timestamp": "2026-02-27T04:44:12+03:00",
          "tree_id": "d2aae4c3fd82bddee7f06b42d095b1b649a7f325",
          "url": "https://github.com/sl4m3/ledgermind/commit/12abfe6c05da7a2e08dc3df2befa57f46ac8c6fb"
        },
        "date": 1772156899633,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 26.12101127913086,
            "unit": "iter/sec",
            "range": "stddev: 0.0036989907762299363",
            "extra": "mean: 38.28335700000025 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 358.6138595522741,
            "unit": "iter/sec",
            "range": "stddev: 0.0003510405423923188",
            "extra": "mean: 2.788514647059347 msec\nrounds: 102"
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
          "id": "c584e219003e6bbe030af00e57c044ca45f4281d",
          "message": "chore: add src to pytest pythonpath in pyproject.toml",
          "timestamp": "2026-02-27T04:45:24+03:00",
          "tree_id": "54a954ba62a8570708ade91275b56602788a5d6d",
          "url": "https://github.com/sl4m3/ledgermind/commit/c584e219003e6bbe030af00e57c044ca45f4281d"
        },
        "date": 1772156996381,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 22.153799572246918,
            "unit": "iter/sec",
            "range": "stddev: 0.00404396212993496",
            "extra": "mean: 45.13898379999546 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_decisions",
            "value": 221.6627766343484,
            "unit": "iter/sec",
            "range": "stddev: 0.0005015532828584892",
            "extra": "mean: 4.511357365380229 msec\nrounds: 52"
          }
        ]
      }
    ]
  }
}