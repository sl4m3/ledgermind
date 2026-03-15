window.BENCHMARK_DATA = {
  "lastUpdate": 1773592724092,
  "repoUrl": "https://github.com/sl4m3/ledgermind",
  "entries": {
    "Benchmark": [
      {
        "commit": {
          "author": {
            "email": "staszotov555@gmail.com",
            "name": "Stanislav Zotov",
            "username": "sl4m3"
          },
          "committer": {
            "email": "staszotov555@gmail.com",
            "name": "Stanislav Zotov",
            "username": "sl4m3"
          },
          "distinct": true,
          "id": "8dc79226a25440db61b87e8d5e967fdd3bb4b878",
          "message": "chore: untrack .jules and scripts folders",
          "timestamp": "2026-03-15T03:50:31+03:00",
          "tree_id": "2be553a4d6e44281c84f34c9cd8792491f96d79c",
          "url": "https://github.com/sl4m3/ledgermind/commit/8dc79226a25440db61b87e8d5e967fdd3bb4b878"
        },
        "date": 1773536773872,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 123.4097694777429,
            "unit": "iter/sec",
            "range": "stddev: 0.00006428139772716505",
            "extra": "mean: 8.103086199997733 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 12494.315087747427,
            "unit": "iter/sec",
            "range": "stddev: 0.000017405047342065124",
            "extra": "mean: 80.0363999928777 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1093.5783765398935,
            "unit": "iter/sec",
            "range": "stddev: 0.000096357763950357",
            "extra": "mean: 914.4292000030418 usec\nrounds: 5"
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
          "id": "c451610faf00e64caa28280f33a089af6d03181d",
          "message": "🛡️ Sentinel: [HIGH] Fix command injection vulnerability (#80)\n\nFixed a potential command injection vulnerability in `src/ledgermind/server/background.py` where `subprocess.run` was using `shell=True`.\nReplaced it with a secure list-based argument passing and resolved the absolute path using `shutil.which`.",
          "timestamp": "2026-03-15T06:17:31-05:00",
          "tree_id": "c5356b7744a07aa5a27a0b78eeab9184d0710473",
          "url": "https://github.com/sl4m3/ledgermind/commit/c451610faf00e64caa28280f33a089af6d03181d"
        },
        "date": 1773573588611,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 93.2764558379404,
            "unit": "iter/sec",
            "range": "stddev: 0.00012041527484068217",
            "extra": "mean: 10.720818999999437 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11780.9774907417,
            "unit": "iter/sec",
            "range": "stddev: 0.000010851567714709438",
            "extra": "mean: 84.88260000376613 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1016.302301966231,
            "unit": "iter/sec",
            "range": "stddev: 0.000125479672352568",
            "extra": "mean: 983.9591999991626 usec\nrounds: 5"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "staszotov555@gmail.com",
            "name": "Stanislav Zotov",
            "username": "sl4m3"
          },
          "committer": {
            "email": "staszotov555@gmail.com",
            "name": "Stanislav Zotov",
            "username": "sl4m3"
          },
          "distinct": true,
          "id": "44060cd58106f6f48ccd43f85da36e3369d2be61",
          "message": "release: version 3.3.3 - interactive settings, openrouter fixes, and robust parsing",
          "timestamp": "2026-03-15T19:24:02+03:00",
          "tree_id": "9fbac3e7389b8b9af3e7078bc0c49aac15944cb4",
          "url": "https://github.com/sl4m3/ledgermind/commit/44060cd58106f6f48ccd43f85da36e3369d2be61"
        },
        "date": 1773591997858,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 94.55223136176677,
            "unit": "iter/sec",
            "range": "stddev: 0.0001521816203320454",
            "extra": "mean: 10.576164999997673 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10549.302163081946,
            "unit": "iter/sec",
            "range": "stddev: 0.000015357309991794846",
            "extra": "mean: 94.79300000521107 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1041.7916816565626,
            "unit": "iter/sec",
            "range": "stddev: 0.00008681671688635798",
            "extra": "mean: 959.8848000109683 usec\nrounds: 5"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "staszotov555@gmail.com",
            "name": "Stanislav Zotov",
            "username": "sl4m3"
          },
          "committer": {
            "email": "staszotov555@gmail.com",
            "name": "Stanislav Zotov",
            "username": "sl4m3"
          },
          "distinct": true,
          "id": "b0065552c5f79188312ad87af747eb4cf972a163",
          "message": "fix(deps): add requests to dependencies",
          "timestamp": "2026-03-15T19:36:22+03:00",
          "tree_id": "37b8c0ae94520acc38329d0c13a5f228556bd70d",
          "url": "https://github.com/sl4m3/ledgermind/commit/b0065552c5f79188312ad87af747eb4cf972a163"
        },
        "date": 1773592723122,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 119.77397979284407,
            "unit": "iter/sec",
            "range": "stddev: 0.0001404939950272498",
            "extra": "mean: 8.3490587999961 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 13065.678551686922,
            "unit": "iter/sec",
            "range": "stddev: 0.0000074791341590119415",
            "extra": "mean: 76.5364000073987 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1086.6265179930017,
            "unit": "iter/sec",
            "range": "stddev: 0.00007633574561571417",
            "extra": "mean: 920.2793999975256 usec\nrounds: 5"
          }
        ]
      }
    ]
  }
}