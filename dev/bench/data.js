window.BENCHMARK_DATA = {
  "lastUpdate": 1773663287047,
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
          "id": "a4f59ca8f0cda1930a2bbd0d346a2c7265b8f6f9",
          "message": "Merge develop/critical-fixes into main - Performance & Health Optimizations (#91)\n\n* 🛡️ Sentinel: [HIGH] Fix command injection vulnerability (#80)\n\nFixed a potential command injection vulnerability in `src/ledgermind/server/background.py` where `subprocess.run` was using `shell=True`.\nReplaced it with a secure list-based argument passing and resolved the absolute path using `shutil.which`.\n\n* fix(cli): resolve AttributeError in settings and implement interactive mode\n\n* release: version 3.3.3 - interactive settings, openrouter fixes, and robust parsing\n\n* fix(deps): add requests to dependencies\n\n* 🧹 Remove unused 'shutil' import in memory API\n\n🎯 What: Removed an unused `import shutil` from `src/ledgermind/core/api/memory.py`.\n💡 Why: Improves code cleanliness and maintainability by removing unnecessary dependencies and dead code.\n✅ Verification: Ran `make test` locally, which passed all relevant tests without introducing any new issues. Also successfully verified with the code reviewer.\n✨ Result: `memory.py` is cleaner, and there's less noise for static analysis tools to report on.\n\n* Remove unused imports in episodic store\n\nRemoved unused `text` import from sqlalchemy, as well as `Session`, `ErrorCode`, and `unwrap_result` which were not used in `src/ledgermind/core/stores/episodic.py`. Fixed PEP8 multiple statements on one line errors.\n\n* 🧹 code health: remove unused imports and fix bare except in trajectory.py\n\n* 🧹 [code health improvement] Remove dead code in query.py\n\nRemoved commented-out legacy code handling draft proposals in balanced mode to improve code maintainability and cleanliness. Evaluated risk, no logical functionality impacted. Format validated via auto-formatter.\n\n* Optimize health check error logging loop\\n\\nReplaces the O(N) multi-log for-loop over `results['errors']` in `health.py` with a single highly efficient string join call.\n\n* Remove unused import `shutil` in transfer.py\n\n* 🧹 [Remove unused import `shutil` in `src/ledgermind/core/api/memory.py`]\n\n* ⚡ Bolt: [performance improvement] optimize current_layer_ids resolution in query.py\n\nOptimized string concatenation and loop generation inside `query.py` `search` function.\n\n💡 **What:**\nReplaced the two-step list comprehensions filtering `current_layer_ids` with a single-pass `list({...})` set comprehension to extract `superseded_by` IDs, filter out missing values, ensure they're not in `request_cache`, and guarantee unique IDs for bulk DB queries.\n\n🎯 **Why:**\nThe original implementation created an intermediate list to collect raw string IDs and then performed another iteration (with additional `in` lookups and unneeded intermediate list allocations) to filter them. The inner loop generated those lists repeatedly. A set comprehension eliminates intermediate list allocations and automatically deduplicates IDs, which drastically reduces inputs to subsequent `get_batch_by_fids` queries.\n\n📊 **Measured Improvement:**\nBenchmarked using mocked list structures overlapping with request caches:\n* Original Loop Time: 1.616s\n* Optimized Set Comprehension Time: 0.792s\n\nThis is an overall ~50% speedup on loop resolution for highly overlapping superseded nodes in local benchmarks, directly dropping unnecessary intermediate iterations and duplications.\n\n* test: Add tests for FastAPI health endpoints\n\n- Add `tests/server/test_health.py`\n- Mock backend resources correctly (`_check_database`, `_check_filesystem`, etc)\n- Added coverage for `/`, `/ready`, `/live`, and `/dependencies` endpoints\n- Fixed flaky/failing logic in `test_advanced_reasoning.py` and `test_bridge.py` related to mocking vector search.\n\n* Optimize HealthService.get_statistics using collections.Counter\n\n- Replaced manual for loop dictionary initialization with `collections.Counter` and generator expressions.\n- Fixed mock encoding issues in vector tests to pass the test suite properly without AxisErrors.\n\n* Fix mock vectors in tests to resolve axis error\n\n- Updated the `mock_encode` lambda in tests to return a valid 1D or 2D NumPy array depending on the input being a string or list of strings to fix the `AxisError` when computing L2 norms.\n- Updated `test_bridge.py` test_record_and_get_context to accurately patch `search_decisions` rather than relying entirely on integration flow without correct real mock setups.",
          "timestamp": "2026-03-15T23:21:55+03:00",
          "tree_id": "1b3360eca1d9436ca74feb0d20503942b793afb2",
          "url": "https://github.com/sl4m3/ledgermind/commit/a4f59ca8f0cda1930a2bbd0d346a2c7265b8f6f9"
        },
        "date": 1773606254967,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 93.27086001383844,
            "unit": "iter/sec",
            "range": "stddev: 0.00006547268489189301",
            "extra": "mean: 10.721462200001497 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11632.99303046833,
            "unit": "iter/sec",
            "range": "stddev: 0.000009511472615247205",
            "extra": "mean: 85.96239999292266 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1034.363628461722,
            "unit": "iter/sec",
            "range": "stddev: 0.00009464495934886708",
            "extra": "mean: 966.7780000029325 usec\nrounds: 5"
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
          "id": "cbc478e252b5380c1d1193ef0550213854a7420d",
          "message": "Remove dead _load_model code in JinaEmbeddingModel",
          "timestamp": "2026-03-16T01:05:49+03:00",
          "tree_id": "9f2f342adb992bdc2f4c8d78518ea2e3cedab28d",
          "url": "https://github.com/sl4m3/ledgermind/commit/cbc478e252b5380c1d1193ef0550213854a7420d"
        },
        "date": 1773612496352,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 90.29755808492062,
            "unit": "iter/sec",
            "range": "stddev: 0.0001102555111956049",
            "extra": "mean: 11.074496600002703 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10530.106628848027,
            "unit": "iter/sec",
            "range": "stddev: 0.000025428935579390996",
            "extra": "mean: 94.9657999910869 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1034.0951512340148,
            "unit": "iter/sec",
            "range": "stddev: 0.00009556087896985419",
            "extra": "mean: 967.0289999974102 usec\nrounds: 5"
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
          "id": "14514c6dbf3a9e00a6a378bde71e6d5ffe483ca2",
          "message": "feat: implement namespace isolation for multi-client support\n\n- Add namespace parameter to Bridge API for client isolation\n- Use --cli flag as namespace in bridge-context/sync/record commands\n- Hooks automatically pass --cli (claude/gemini/cursor) as namespace\n- Each client works with isolated namespace in shared memory\n- Add comprehensive test coverage for namespace isolation\n\nChanges:\n- src/ledgermind/core/api/bridge.py: Add namespace parameter\n- src/ledgermind/server/cli.py: Use --cli as namespace\n- src/ledgermind/server/server.py: Pass client to background worker\n- src/ledgermind/server/background.py: Support client parameter\n- src/ledgermind/server/installers.py: Include --cli in hooks\n- tests/core/test_bridge_namespace.py: Bridge namespace tests (5 tests)\n- tests/server/test_cli_namespace.py: CLI namespace tests (4 tests)\n- tests/server/test_hooks_namespace.py: Hook namespace tests (7 tests)\n- tests/core/test_multi_client_namespace.py: Multi-client tests (4 tests)\n\nTesting:\n- All 321 tests passing\n- Namespace isolation verified for claude/gemini/cursor\n- Concurrent clients with different namespaces don't interfere",
          "timestamp": "2026-03-16T03:59:54+03:00",
          "tree_id": "fa981faec504ec0bbfca46b9db517e10f2a42518",
          "url": "https://github.com/sl4m3/ledgermind/commit/14514c6dbf3a9e00a6a378bde71e6d5ffe483ca2"
        },
        "date": 1773623827624,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 92.42067985907875,
            "unit": "iter/sec",
            "range": "stddev: 0.00037337628445395553",
            "extra": "mean: 10.820089200001348 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11251.403612733053,
            "unit": "iter/sec",
            "range": "stddev: 0.000012048500366411772",
            "extra": "mean: 88.87779999895429 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1033.3364677895372,
            "unit": "iter/sec",
            "range": "stddev: 0.00009066293190457951",
            "extra": "mean: 967.7389999978914 usec\nrounds: 5"
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
          "id": "dc2bac16424b2ba49cd5b9a1aa31936272777008",
          "message": "⚡ Bolt: Optimize hierarchical ID resolution (#93)\n\n* ⚡ Bolt: Optimize hierarchical ID resolution\n\n💡 **What:** Optimized `current_layer_ids` resolution by replacing two-pass list comprehensions with single-pass `list(dict.fromkeys(...))`.\n🎯 **Why:** To eliminate redundant intermediate list allocations, speed up iterative layer fetching, and cleanly deduplicate database inputs while preserving deterministic fetching order.\n📊 **Impact:** Reduces redundant memory allocations per layer resolution and safely prevents duplicate DB fetches during recursive truth resolution.\n🔬 **Measurement:** Search queries spanning deep `superseded_by` chains.\n\n* Delete .jules/bolt.md",
          "timestamp": "2026-03-16T15:12:10+03:00",
          "tree_id": "581af15ca4e532728fd7744c7e16546d13bebdb5",
          "url": "https://github.com/sl4m3/ledgermind/commit/dc2bac16424b2ba49cd5b9a1aa31936272777008"
        },
        "date": 1773663274750,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 95.4891626198021,
            "unit": "iter/sec",
            "range": "stddev: 0.00008625236826863113",
            "extra": "mean: 10.472392600001967 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10563.521624388854,
            "unit": "iter/sec",
            "range": "stddev: 0.000017118938649488815",
            "extra": "mean: 94.66540000175883 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1024.4331401651623,
            "unit": "iter/sec",
            "range": "stddev: 0.00010134362480431214",
            "extra": "mean: 976.1496000010084 usec\nrounds: 5"
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
          "id": "9e3ab96b1ebb650bf6f45cf60f0d1b409d236a7f",
          "message": "🛡️ Sentinel: [Low] Fix subprocess command injection risks (#94)",
          "timestamp": "2026-03-16T15:12:27+03:00",
          "tree_id": "5a55ac3256d74fef35cc0492689eed6c6b8dd684",
          "url": "https://github.com/sl4m3/ledgermind/commit/9e3ab96b1ebb650bf6f45cf60f0d1b409d236a7f"
        },
        "date": 1773663286681,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 90.1323776031285,
            "unit": "iter/sec",
            "range": "stddev: 0.00007380933377430042",
            "extra": "mean: 11.094792200015036 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 12073.736726725676,
            "unit": "iter/sec",
            "range": "stddev: 0.000011403857577847332",
            "extra": "mean: 82.82439998765767 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1104.562528088434,
            "unit": "iter/sec",
            "range": "stddev: 0.00008750016614998276",
            "extra": "mean: 905.3357999846412 usec\nrounds: 5"
          }
        ]
      }
    ]
  }
}