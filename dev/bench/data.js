window.BENCHMARK_DATA = {
  "lastUpdate": 1772075114301,
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
      }
    ]
  }
}