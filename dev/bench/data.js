window.BENCHMARK_DATA = {
  "lastUpdate": 1776597678504,
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
          "id": "6e9dd4673dcfe1d6d01138b4411aa61766dcea6e",
          "message": "release: version 3.3.4 - namespace isolation, security hardening, and client-specific models",
          "timestamp": "2026-03-16T21:46:39+03:00",
          "tree_id": "2d490b02f8267f8e60df121d2f42e5bb214ba544",
          "url": "https://github.com/sl4m3/ledgermind/commit/6e9dd4673dcfe1d6d01138b4411aa61766dcea6e"
        },
        "date": 1773686970423,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 93.10669673636608,
            "unit": "iter/sec",
            "range": "stddev: 0.00015700445056212708",
            "extra": "mean: 10.740366000004542 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11506.950198701772,
            "unit": "iter/sec",
            "range": "stddev: 0.00000940711079549277",
            "extra": "mean: 86.90399999409237 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1020.1945470254909,
            "unit": "iter/sec",
            "range": "stddev: 0.00010450286478214682",
            "extra": "mean: 980.2051999940886 usec\nrounds: 5"
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
          "id": "f03afb1258891f80715e95c0545f3c98355efedb",
          "message": "release: version 3.3.5 - Google AI Studio integration, Claude CLI optimization, and robust API key management",
          "timestamp": "2026-03-17T01:20:04+03:00",
          "tree_id": "d4341ae5326b1398456256219a962ca4231c8288",
          "url": "https://github.com/sl4m3/ledgermind/commit/f03afb1258891f80715e95c0545f3c98355efedb"
        },
        "date": 1773699782776,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 86.10391033671019,
            "unit": "iter/sec",
            "range": "stddev: 0.00019598277318422978",
            "extra": "mean: 11.613874400006807 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10253.465670439575,
            "unit": "iter/sec",
            "range": "stddev: 0.00001516086296720346",
            "extra": "mean: 97.52800000910611 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1003.9727200611717,
            "unit": "iter/sec",
            "range": "stddev: 0.00009525679458842473",
            "extra": "mean: 996.0429999921415 usec\nrounds: 5"
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
          "id": "3ca06b7e1ccdd43b9b4465653e400fb8ccaca583",
          "message": "feat: add \"enrichment\" as a valid memory event source\n\n- Update MemoryEvent schema to include \"enrichment\" source.\n- Allow memory writes from \"enrichment\" source while background worker is active.\n- Add optional \"source\" parameter to supersede_decision method.\n- Use source=\"enrichment\" in LLMEnricher when creating new decisions.",
          "timestamp": "2026-03-17T02:10:38+03:00",
          "tree_id": "25a7e6a5ba06915907b0ae629b1b6ae627b9c8a1",
          "url": "https://github.com/sl4m3/ledgermind/commit/3ca06b7e1ccdd43b9b4465653e400fb8ccaca583"
        },
        "date": 1773702845576,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 93.23902566412029,
            "unit": "iter/sec",
            "range": "stddev: 0.00009655623177524715",
            "extra": "mean: 10.725122799999554 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10332.200922119187,
            "unit": "iter/sec",
            "range": "stddev: 0.000017541676273309918",
            "extra": "mean: 96.78480001866774 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1030.7943631247033,
            "unit": "iter/sec",
            "range": "stddev: 0.00009053826195801288",
            "extra": "mean: 970.1255999971181 usec\nrounds: 5"
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
          "id": "6988b2a15dda2531cee15f1ddf4d26efeb9dd820",
          "message": "🎨 Palette: fix accessibility spam and replace error popups with output channel (#95)",
          "timestamp": "2026-03-18T06:54:52-05:00",
          "tree_id": "9e127d9851556bb682f860870460f5c35d8f28ad",
          "url": "https://github.com/sl4m3/ledgermind/commit/6988b2a15dda2531cee15f1ddf4d26efeb9dd820"
        },
        "date": 1773835036189,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 94.63688781981823,
            "unit": "iter/sec",
            "range": "stddev: 0.00017523437477474704",
            "extra": "mean: 10.566704199993637 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10651.873346816103,
            "unit": "iter/sec",
            "range": "stddev: 0.000027828890554307325",
            "extra": "mean: 93.88019998368691 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1037.8111980688009,
            "unit": "iter/sec",
            "range": "stddev: 0.0000977235690709999",
            "extra": "mean: 963.5663999972621 usec\nrounds: 5"
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
          "id": "0a44df74adb398d5976315946ef5e1305b28a4ef",
          "message": "⚡ Bolt: Chunk SQLite batch operations (#96)\n\nOptimizes `SemanticMetaStore.get_batch_by_fids` by chunking `IN (...)` queries to prevent `OperationalError` from SQLite's host parameter limit (typically 999).",
          "timestamp": "2026-03-19T16:11:11+03:00",
          "tree_id": "fc79fd9ec7ed4e9b9d351c41ba9a8bcc2430f4cf",
          "url": "https://github.com/sl4m3/ledgermind/commit/0a44df74adb398d5976315946ef5e1305b28a4ef"
        },
        "date": 1773926020097,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 122.88691042037689,
            "unit": "iter/sec",
            "range": "stddev: 0.00018816574590420557",
            "extra": "mean: 8.137563200011755 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 13297.483317798393,
            "unit": "iter/sec",
            "range": "stddev: 0.000007703865180793589",
            "extra": "mean: 75.20220000287736 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1067.1073962367038,
            "unit": "iter/sec",
            "range": "stddev: 0.00010757686328602901",
            "extra": "mean: 937.1128000111639 usec\nrounds: 5"
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
          "id": "dc20aa9cc4b5e6fca86ecd045e6486bb466f1777",
          "message": "⚡ Bolt: Optimize SQLite batch queries using json_each (#97)",
          "timestamp": "2026-03-20T07:44:55-05:00",
          "tree_id": "d61a96b284c9e446acfa2437dac16841df12e565",
          "url": "https://github.com/sl4m3/ledgermind/commit/dc20aa9cc4b5e6fca86ecd045e6486bb466f1777"
        },
        "date": 1774010835477,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 92.98917938851969,
            "unit": "iter/sec",
            "range": "stddev: 0.00023389602624118998",
            "extra": "mean: 10.7539394000014 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11396.063340357785,
            "unit": "iter/sec",
            "range": "stddev: 0.000009619035548180096",
            "extra": "mean: 87.74960002710941 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1002.8456748925685,
            "unit": "iter/sec",
            "range": "stddev: 0.00009602619915861379",
            "extra": "mean: 997.1623999945223 usec\nrounds: 5"
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
          "id": "c4b07595e54e091f8dab6dd49bf1d687e2f8286b",
          "message": "🛡️ Sentinel: Fix Bandit B607 in EnvironmentContext (#98)",
          "timestamp": "2026-03-20T07:45:11-05:00",
          "tree_id": "247731da4a2afed51331c6a64ddac22f22015fad",
          "url": "https://github.com/sl4m3/ledgermind/commit/c4b07595e54e091f8dab6dd49bf1d687e2f8286b"
        },
        "date": 1774010846360,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 88.34702400037831,
            "unit": "iter/sec",
            "range": "stddev: 0.00013502061456663176",
            "extra": "mean: 11.319000400010282 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10473.222065314016,
            "unit": "iter/sec",
            "range": "stddev: 0.00001670392574164512",
            "extra": "mean: 95.48160000463213 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1024.5826055375314,
            "unit": "iter/sec",
            "range": "stddev: 0.00008470691930093865",
            "extra": "mean: 976.0072000005948 usec\nrounds: 5"
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
          "id": "d8c7961246c44d3a8c8c2aab08ae25d2258fadf4",
          "message": "Optimize batch database operations by deduplicating input IDs (#99)",
          "timestamp": "2026-03-21T07:03:52-05:00",
          "tree_id": "075ccb5176d231d1d73f85d76f39053351de7287",
          "url": "https://github.com/sl4m3/ledgermind/commit/d8c7961246c44d3a8c8c2aab08ae25d2258fadf4"
        },
        "date": 1774094766048,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 95.87219944364236,
            "unit": "iter/sec",
            "range": "stddev: 0.00007877073135725441",
            "extra": "mean: 10.430552399998305 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10713.956641969564,
            "unit": "iter/sec",
            "range": "stddev: 0.000016484263637333237",
            "extra": "mean: 93.33620000688825 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 936.8678484232423,
            "unit": "iter/sec",
            "range": "stddev: 0.00010051138346787926",
            "extra": "mean: 1.0673863999954847 msec\nrounds: 5"
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
          "id": "d82cf00eb9acf351fd77cd6b10464a28169e6a9d",
          "message": "🛡️ Sentinel: [MEDIUM] Fix Path Hijacking in Subprocess calls (#101)",
          "timestamp": "2026-03-22T06:22:18-05:00",
          "tree_id": "8705fca6af453a40b34acaa9001bd6337ddecffe",
          "url": "https://github.com/sl4m3/ledgermind/commit/d82cf00eb9acf351fd77cd6b10464a28169e6a9d"
        },
        "date": 1774178671113,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 111.9307175720496,
            "unit": "iter/sec",
            "range": "stddev: 0.00009162470233703653",
            "extra": "mean: 8.934098000008817 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 13170.71885791739,
            "unit": "iter/sec",
            "range": "stddev: 0.000007871057708524503",
            "extra": "mean: 75.92599999952654 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1057.7215577408424,
            "unit": "iter/sec",
            "range": "stddev: 0.00009491050097991681",
            "extra": "mean: 945.4284000184998 usec\nrounds: 5"
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
          "id": "4f074e1489b6b266f1f333375e231ddb8d877e32",
          "message": "⚡ Bolt: Resolve N+1 query bottleneck by using batch updates during event processing (#100)",
          "timestamp": "2026-03-22T06:22:07-05:00",
          "tree_id": "9717f138cb771f5795b4403a21331c2b4f5f40f4",
          "url": "https://github.com/sl4m3/ledgermind/commit/4f074e1489b6b266f1f333375e231ddb8d877e32"
        },
        "date": 1774178675268,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 88.87517762143176,
            "unit": "iter/sec",
            "range": "stddev: 0.0002630740233321003",
            "extra": "mean: 11.251735600006896 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 6196.631511275932,
            "unit": "iter/sec",
            "range": "stddev: 0.000024231545762108695",
            "extra": "mean: 161.37799999569324 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 931.4103807196134,
            "unit": "iter/sec",
            "range": "stddev: 0.00013199228715844664",
            "extra": "mean: 1.073640599997816 msec\nrounds: 5"
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
          "id": "f84758b51c26117b99dfcf1ec964cff6f52c5672",
          "message": "⚡ Bolt: Ensure keyword_search uses retry logic to maintain Fast Path performance (#102)",
          "timestamp": "2026-03-22T16:05:14+03:00",
          "tree_id": "cd28af410f83b6dc82ea386f98e88587b4efc7f4",
          "url": "https://github.com/sl4m3/ledgermind/commit/f84758b51c26117b99dfcf1ec964cff6f52c5672"
        },
        "date": 1774184868549,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 86.67733780267159,
            "unit": "iter/sec",
            "range": "stddev: 0.00032390577846716533",
            "extra": "mean: 11.537040999996862 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10295.331890340549,
            "unit": "iter/sec",
            "range": "stddev: 0.000014849415332875922",
            "extra": "mean: 97.13140000258136 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1005.5937156441029,
            "unit": "iter/sec",
            "range": "stddev: 0.00009410246574902397",
            "extra": "mean: 994.4373999587696 usec\nrounds: 5"
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
          "id": "8d2b5f79b3c74998b34bb8cdc15622a690eb7f56",
          "message": "⚡ Bolt: Batch metadata lookups in enrichment validation (#102)",
          "timestamp": "2026-03-23T06:59:13-05:00",
          "tree_id": "ff8a1de682b40a539a4907f8a579bef3188626a3",
          "url": "https://github.com/sl4m3/ledgermind/commit/8d2b5f79b3c74998b34bb8cdc15622a690eb7f56"
        },
        "date": 1774267384320,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 90.87135286238048,
            "unit": "iter/sec",
            "range": "stddev: 0.00015424663644887358",
            "extra": "mean: 11.004568199996356 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11244.470532432759,
            "unit": "iter/sec",
            "range": "stddev: 0.000011553907420360002",
            "extra": "mean: 88.93259999354086 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 972.0612110815351,
            "unit": "iter/sec",
            "range": "stddev: 0.00009610445881737054",
            "extra": "mean: 1.0287418000018533 msec\nrounds: 5"
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
          "id": "0d8296ee0ee6423c671709b7573ef1f46f178393",
          "message": "⚡ Bolt: [performance improvement] fix N+1 query issue during grounding links inheritance (#103)",
          "timestamp": "2026-03-24T06:30:23-05:00",
          "tree_id": "7b3a7fcb7d28217d8d356cdfe6e7da74224b921b",
          "url": "https://github.com/sl4m3/ledgermind/commit/0d8296ee0ee6423c671709b7573ef1f46f178393"
        },
        "date": 1774352038898,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 92.89199553591818,
            "unit": "iter/sec",
            "range": "stddev: 0.00023171483442140813",
            "extra": "mean: 10.765190199981589 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11298.311581536524,
            "unit": "iter/sec",
            "range": "stddev: 0.000009670906613430035",
            "extra": "mean: 88.50879999044992 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 998.6715670753614,
            "unit": "iter/sec",
            "range": "stddev: 0.00009028683582540328",
            "extra": "mean: 1.001330200006123 msec\nrounds: 5"
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
          "id": "5cdc5393ca503d69021ac627798081f864057c21",
          "message": "🛡️ Sentinel: [CRITICAL] Add authentication to admin endpoint (#106)",
          "timestamp": "2026-03-27T06:15:55-05:00",
          "tree_id": "41cb2def5bba6111bf2ec4f3383eb54176c36831",
          "url": "https://github.com/sl4m3/ledgermind/commit/5cdc5393ca503d69021ac627798081f864057c21"
        },
        "date": 1774610371070,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 99.56480621462079,
            "unit": "iter/sec",
            "range": "stddev: 0.00009135177167400391",
            "extra": "mean: 10.043709600000739 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11361.13175063157,
            "unit": "iter/sec",
            "range": "stddev: 0.000012651314701667057",
            "extra": "mean: 88.01939999898423 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 993.249676548863,
            "unit": "iter/sec",
            "range": "stddev: 0.00009882642068825327",
            "extra": "mean: 1.0067961999993713 msec\nrounds: 5"
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
          "id": "b396f4e83f4f7c6b40bf6d7e9101174369a0b850",
          "message": "refactor(core): batch fetch metadata in decision command (#105)",
          "timestamp": "2026-03-27T06:15:46-05:00",
          "tree_id": "e6f709e6431fa02b98414810e55c4d7b9550dbed",
          "url": "https://github.com/sl4m3/ledgermind/commit/b396f4e83f4f7c6b40bf6d7e9101174369a0b850"
        },
        "date": 1774610386569,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 96.50200497388192,
            "unit": "iter/sec",
            "range": "stddev: 0.0006344674562585787",
            "extra": "mean: 10.362479000002622 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11371.467171159464,
            "unit": "iter/sec",
            "range": "stddev: 0.000009630527640817502",
            "extra": "mean: 87.93939998668066 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 993.3299877904773,
            "unit": "iter/sec",
            "range": "stddev: 0.00009233367236628183",
            "extra": "mean: 1.0067148000075576 msec\nrounds: 5"
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
          "id": "f27a83e1faf6ba027474e0cd1b524e571e0a0929",
          "message": "⚡ Bolt: Resolve N+1 query bottlenecks in enrichment facade (#107)",
          "timestamp": "2026-03-28T08:28:12-05:00",
          "tree_id": "83a7df259ea2ef7a0c0a97644458cec2e1c5a88e",
          "url": "https://github.com/sl4m3/ledgermind/commit/f27a83e1faf6ba027474e0cd1b524e571e0a0929"
        },
        "date": 1774704711405,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 99.61576406717124,
            "unit": "iter/sec",
            "range": "stddev: 0.00014241252307322006",
            "extra": "mean: 10.038571799998408 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10920.511779108108,
            "unit": "iter/sec",
            "range": "stddev: 0.00001000465709882566",
            "extra": "mean: 91.57079999795315 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 955.6563964185137,
            "unit": "iter/sec",
            "range": "stddev: 0.0001182469755735628",
            "extra": "mean: 1.0464011999999911 msec\nrounds: 5"
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
          "id": "f1ce87d4273ed7738a534737b472c6fad7e14c32",
          "message": "🛡️ Sentinel: [MEDIUM] Fix insecure subprocess execution (#108)",
          "timestamp": "2026-03-28T08:28:25-05:00",
          "tree_id": "b85f5c5e8318c0cbcb919a90c5e7c61aa0b00192",
          "url": "https://github.com/sl4m3/ledgermind/commit/f1ce87d4273ed7738a534737b472c6fad7e14c32"
        },
        "date": 1774704740923,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 95.03033358743353,
            "unit": "iter/sec",
            "range": "stddev: 0.0001297654303514476",
            "extra": "mean: 10.52295580000191 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10234.367004400106,
            "unit": "iter/sec",
            "range": "stddev: 0.000026706970550501557",
            "extra": "mean: 97.7100000000064 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 946.6473348661402,
            "unit": "iter/sec",
            "range": "stddev: 0.00009539032418703366",
            "extra": "mean: 1.0563595999997233 msec\nrounds: 5"
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
          "id": "6e9f815be99694a7b640242b7f084b5086a56739",
          "message": "🛡️ Sentinel: [HIGH] Fix insecure subprocess execution (#109)",
          "timestamp": "2026-03-29T06:30:30-05:00",
          "tree_id": "0e3b03a09e22cbf23ca289f5ac07a24731a29d51",
          "url": "https://github.com/sl4m3/ledgermind/commit/6e9f815be99694a7b640242b7f084b5086a56739"
        },
        "date": 1774784053681,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 93.45225294508354,
            "unit": "iter/sec",
            "range": "stddev: 0.00008488059346116775",
            "extra": "mean: 10.700651599995581 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 9753.261980073386,
            "unit": "iter/sec",
            "range": "stddev: 0.000021222302181958405",
            "extra": "mean: 102.52979998313094 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 950.5134198261023,
            "unit": "iter/sec",
            "range": "stddev: 0.00011494079516671869",
            "extra": "mean: 1.0520629999973607 msec\nrounds: 5"
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
          "id": "697d103c0d443675828d439d5dc343a6273930e9",
          "message": "🛡️ Sentinel: [CRITICAL] Fix insecure subprocess execution in bridge API (#110)\n\n🚨 Severity: CRITICAL\n💡 Vulnerability: Unresolved paths in subprocess execution (B603)\n🎯 Impact: Command injection risk and unintended binary execution\n🔧 Fix: Added `shutil.which` resolution and `# nosec B603`\n✅ Verification: `make test` and `make lint` pass",
          "timestamp": "2026-03-30T06:39:20-05:00",
          "tree_id": "317ba6c5bd5f0d8e138794f2921d71a1a6f70400",
          "url": "https://github.com/sl4m3/ledgermind/commit/697d103c0d443675828d439d5dc343a6273930e9"
        },
        "date": 1774870983595,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 94.96685903538176,
            "unit": "iter/sec",
            "range": "stddev: 0.00019730903999551304",
            "extra": "mean: 10.529989199994816 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10478.621516164609,
            "unit": "iter/sec",
            "range": "stddev: 0.000023789234848728194",
            "extra": "mean: 95.43240000198239 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1004.4291306966924,
            "unit": "iter/sec",
            "range": "stddev: 0.00009681482272272466",
            "extra": "mean: 995.5903999980364 usec\nrounds: 5"
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
          "id": "0c9dc6bbc917d1cf45659eea0006ebb2e78a44fe",
          "message": "⚡ Bolt: Prevent N+1 queries during metadata fetching in background processing loops (#111)",
          "timestamp": "2026-04-01T06:34:24-05:00",
          "tree_id": "854dd866620695ea7f200d09285082c44f068fed",
          "url": "https://github.com/sl4m3/ledgermind/commit/0c9dc6bbc917d1cf45659eea0006ebb2e78a44fe"
        },
        "date": 1775043483916,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 100.23279869354955,
            "unit": "iter/sec",
            "range": "stddev: 0.000054842259185792214",
            "extra": "mean: 9.976774200004002 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10404.268247297421,
            "unit": "iter/sec",
            "range": "stddev: 0.000029399846373122155",
            "extra": "mean: 96.11439999730464 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1006.6444574004377,
            "unit": "iter/sec",
            "range": "stddev: 0.00009331305771507806",
            "extra": "mean: 993.3994000050461 usec\nrounds: 5"
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
          "id": "1121bae12897ee947f2f27ca0ea075a429d50842",
          "message": "⚡ Bolt: Prevent N+1 queries in server isolation validation (#112)",
          "timestamp": "2026-04-03T06:43:37-05:00",
          "tree_id": "5c1fc6e9bc7dc2645c17cfc02d141d96f1b0f588",
          "url": "https://github.com/sl4m3/ledgermind/commit/1121bae12897ee947f2f27ca0ea075a429d50842"
        },
        "date": 1775216834876,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 96.52230893095535,
            "unit": "iter/sec",
            "range": "stddev: 0.00025606164672704803",
            "extra": "mean: 10.360299200004874 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11567.08562612064,
            "unit": "iter/sec",
            "range": "stddev: 0.00000988204071383993",
            "extra": "mean: 86.45220000289555 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 966.5920650961141,
            "unit": "iter/sec",
            "range": "stddev: 0.00014799248363911536",
            "extra": "mean: 1.034562599994615 msec\nrounds: 5"
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
          "id": "4773286d1119449e88aed4d6de564d1acee1c6bb",
          "message": "🎨 Palette: Make status bar clickable to show logs (#113)\n\n- Registered `ledgermind.showOutput` command to display the logging channel.\n- Assigned the new command to `statusBarItem.command` so the item acts as a button.\n- Updated the tooltips to explicitly say \"(Click to view logs)\".\n- Updated `accessibilityInformation.label` to provide screen reader users the same contextual action hint.",
          "timestamp": "2026-04-03T06:43:45-05:00",
          "tree_id": "ca52f37dac7fca4486376d358cb46417644e118c",
          "url": "https://github.com/sl4m3/ledgermind/commit/4773286d1119449e88aed4d6de564d1acee1c6bb"
        },
        "date": 1775216835368,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 102.3322648821504,
            "unit": "iter/sec",
            "range": "stddev: 0.00009640137475974783",
            "extra": "mean: 9.772089000000506 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11543.531812571604,
            "unit": "iter/sec",
            "range": "stddev: 0.000011910687653895299",
            "extra": "mean: 86.62860000185901 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 996.7086686441409,
            "unit": "iter/sec",
            "range": "stddev: 0.00010460555143040049",
            "extra": "mean: 1.0033021999902303 msec\nrounds: 5"
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
          "id": "3fff8c393d3aec1eb72fe84d1a5e5316f73c53e4",
          "message": "⚡ Bolt: Eliminate redundant metadata DB query in update_decision (#114)",
          "timestamp": "2026-04-04T06:37:30-05:00",
          "tree_id": "566f6cb559b4c70c3ca55afa564523fa0a63e66f",
          "url": "https://github.com/sl4m3/ledgermind/commit/3fff8c393d3aec1eb72fe84d1a5e5316f73c53e4"
        },
        "date": 1775302863102,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 100.07292113622562,
            "unit": "iter/sec",
            "range": "stddev: 0.00018914994942228406",
            "extra": "mean: 9.992713199994796 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11217.804899532455,
            "unit": "iter/sec",
            "range": "stddev: 0.000013170539546967501",
            "extra": "mean: 89.1440000032162 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1008.0895151163544,
            "unit": "iter/sec",
            "range": "stddev: 0.00008636673538151453",
            "extra": "mean: 991.9754000065951 usec\nrounds: 5"
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
          "id": "174638218f914599e356085425da09c546448bec",
          "message": "fix: mark secure sys.executable subprocess call as false positive for Bandit B603 (#115)",
          "timestamp": "2026-04-04T06:37:39-05:00",
          "tree_id": "3113d7b51564b17460f14befb6a6c38381bb550f",
          "url": "https://github.com/sl4m3/ledgermind/commit/174638218f914599e356085425da09c546448bec"
        },
        "date": 1775302884739,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 100.00475622625005,
            "unit": "iter/sec",
            "range": "stddev: 0.0001010482834829921",
            "extra": "mean: 9.999524399995607 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10396.674728831516,
            "unit": "iter/sec",
            "range": "stddev: 0.000014146158756647385",
            "extra": "mean: 96.18459998819162 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 985.976456850059,
            "unit": "iter/sec",
            "range": "stddev: 0.00008727598078959412",
            "extra": "mean: 1.0142230000042218 msec\nrounds: 5"
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
          "id": "7c10c361dfafc84fcd4ee01a62e31ddd60b9dfb3",
          "message": "🎨 Palette: Add visual error state to status bar (#116)",
          "timestamp": "2026-04-04T06:37:46-05:00",
          "tree_id": "cead93153243d1ece180d80d786689f77be690dd",
          "url": "https://github.com/sl4m3/ledgermind/commit/7c10c361dfafc84fcd4ee01a62e31ddd60b9dfb3"
        },
        "date": 1775302891083,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 99.98483030150493,
            "unit": "iter/sec",
            "range": "stddev: 0.0002870092530585627",
            "extra": "mean: 10.001517200004173 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10288.446898097543,
            "unit": "iter/sec",
            "range": "stddev: 0.000012425973632522103",
            "extra": "mean: 97.196399991617 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1024.7652979988918,
            "unit": "iter/sec",
            "range": "stddev: 0.00008761929897288688",
            "extra": "mean: 975.8332000046721 usec\nrounds: 5"
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
          "id": "08a50c6a304625e2d96bdd2b0f85873f0809f580",
          "message": "fix: Add missing authentication to direct MCP tools (#118)\n\nExplicitly added `self.server._validate_auth()` to all methods in `LedgerMindTools` before capability checks to prevent unauthenticated API access.",
          "timestamp": "2026-04-05T07:02:32-05:00",
          "tree_id": "8ceb4c6b9ab44f4b6b67bd1e1c4f42a968d3e081",
          "url": "https://github.com/sl4m3/ledgermind/commit/08a50c6a304625e2d96bdd2b0f85873f0809f580"
        },
        "date": 1775390769761,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 100.012123469628,
            "unit": "iter/sec",
            "range": "stddev: 0.00007307467809627494",
            "extra": "mean: 9.9987877999979 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10693.654599532212,
            "unit": "iter/sec",
            "range": "stddev: 0.000024390848258606628",
            "extra": "mean: 93.51339999739139 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 999.7358697871197,
            "unit": "iter/sec",
            "range": "stddev: 0.00008731282953657752",
            "extra": "mean: 1.0002641999960815 msec\nrounds: 5"
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
          "id": "482ecbf587c9130965b8dd3c81aa7ec2d758bbea",
          "message": "⚡ Bolt: Fix N+1 query in proposal acceptance by batch fetching metadata (#117)\n\nReplaced iterative loop calls to the non-existent `SemanticStore.get_decision`\nwith a single batch query using `SemanticMetaStore.get_batch_by_fids` to resolve\nthe N+1 database performance bottleneck. Additionally, individual parsing logic\nwas isolated within try...except blocks to prevent failure cascades.",
          "timestamp": "2026-04-05T07:02:23-05:00",
          "tree_id": "c20589c224c754e6eb49e6d4ea9ceeab6abb3a26",
          "url": "https://github.com/sl4m3/ledgermind/commit/482ecbf587c9130965b8dd3c81aa7ec2d758bbea"
        },
        "date": 1775390775845,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 94.3775677658907,
            "unit": "iter/sec",
            "range": "stddev: 0.00018216530270985602",
            "extra": "mean: 10.59573819999855 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10672.836989364567,
            "unit": "iter/sec",
            "range": "stddev: 0.00001678410793618799",
            "extra": "mean: 93.69580000111455 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 997.9294958887912,
            "unit": "iter/sec",
            "range": "stddev: 0.0000668304214620226",
            "extra": "mean: 1.0020747999931245 msec\nrounds: 5"
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
          "id": "68c5e0d6c898c20ec0f5df87f27772115f83866f",
          "message": "feat: add show output command to command palette (#119)\n\nExplicitly declared the ledgermind.showOutput command in package.json to make it accessible via the Command Palette, improving keyboard accessibility.",
          "timestamp": "2026-04-05T07:02:41-05:00",
          "tree_id": "9b17d6a0292e2cd7e45b0302ce1439578858eef9",
          "url": "https://github.com/sl4m3/ledgermind/commit/68c5e0d6c898c20ec0f5df87f27772115f83866f"
        },
        "date": 1775390781136,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 100.26868799771978,
            "unit": "iter/sec",
            "range": "stddev: 0.00012058517968179541",
            "extra": "mean: 9.973203200013359 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11810.83762467264,
            "unit": "iter/sec",
            "range": "stddev: 0.000009717881519203216",
            "extra": "mean: 84.66799999951036 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1013.4213469573722,
            "unit": "iter/sec",
            "range": "stddev: 0.00008500340163482861",
            "extra": "mean: 986.7563999932827 usec\nrounds: 5"
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
          "id": "06fede07ee3315243ea7eff4a0779bc6aca69864",
          "message": "Fix path hijacking vulnerability in git subprocess calls using shutil.which (#121)",
          "timestamp": "2026-04-06T06:23:52-05:00",
          "tree_id": "2af486caae008e9a0782b77f72db4c1aed78c7ff",
          "url": "https://github.com/sl4m3/ledgermind/commit/06fede07ee3315243ea7eff4a0779bc6aca69864"
        },
        "date": 1775474841556,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 118.09611304140513,
            "unit": "iter/sec",
            "range": "stddev: 0.00014372835142482073",
            "extra": "mean: 8.467679199986833 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 12926.008936100154,
            "unit": "iter/sec",
            "range": "stddev: 0.000008093584736515327",
            "extra": "mean: 77.3634000211132 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1009.3542918367921,
            "unit": "iter/sec",
            "range": "stddev: 0.00010361174932193796",
            "extra": "mean: 990.7323999982509 usec\nrounds: 5"
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
          "id": "89372e11dc759f719a56fb74f24b4bd6397944cc",
          "message": "perf(semantic): prevent N+1 queries during meta index sync (#120)\n\nOptimizes `sync_meta_index` by pre-fetching metadata for all disk files\nusing `get_batch_by_fids`, rather than executing a separate query for\neach file during the `_update_meta_for_file` loop.",
          "timestamp": "2026-04-06T06:23:42-05:00",
          "tree_id": "262865f02198089fef294272a1bbb9b545cb2a31",
          "url": "https://github.com/sl4m3/ledgermind/commit/89372e11dc759f719a56fb74f24b4bd6397944cc"
        },
        "date": 1775474851124,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 90.60613200918449,
            "unit": "iter/sec",
            "range": "stddev: 0.0002058064124758558",
            "extra": "mean: 11.036780599999929 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11449.927178641636,
            "unit": "iter/sec",
            "range": "stddev: 0.00000997033940759107",
            "extra": "mean: 87.33679999863853 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 890.8282814510218,
            "unit": "iter/sec",
            "range": "stddev: 0.00009993287736892318",
            "extra": "mean: 1.12255079999386 msec\nrounds: 5"
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
          "id": "614d83a3f1e3d394834e05adfae7d3a8c8361719",
          "message": "Fix path traversal vulnerability in purge_memory (#123)\n\nAdded _validate_fid call to sanitize incoming file IDs before\nexecuting file system operations like os.remove and os.path.join.",
          "timestamp": "2026-04-07T06:16:52-05:00",
          "tree_id": "b0f243fe7389df6b5e35fa8636b4096a6e86aedd",
          "url": "https://github.com/sl4m3/ledgermind/commit/614d83a3f1e3d394834e05adfae7d3a8c8361719"
        },
        "date": 1775560838291,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 95.96327416406223,
            "unit": "iter/sec",
            "range": "stddev: 0.00015913795225172835",
            "extra": "mean: 10.420653199997787 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11409.35156098255,
            "unit": "iter/sec",
            "range": "stddev: 0.000011473069210810404",
            "extra": "mean: 87.64739999946869 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 986.389599039803,
            "unit": "iter/sec",
            "range": "stddev: 0.00008794242981674869",
            "extra": "mean: 1.0137981999946533 msec\nrounds: 5"
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
          "id": "f0bad2913002d07aa5135fbd957dec79fa448f6e",
          "message": "Improve CLI output feedback for JSON parse errors (#124)\n\n- Add module-level logger to `cli.py`\n- Catch and log `json.JSONDecodeError` instead of silently ignoring it\n- Helps users identify malformed JSON inputs when piping data or invoking the CLI",
          "timestamp": "2026-04-07T06:17:00-05:00",
          "tree_id": "35eb63552d0f668b408cd66bfe2fb9bd35bf2862",
          "url": "https://github.com/sl4m3/ledgermind/commit/f0bad2913002d07aa5135fbd957dec79fa448f6e"
        },
        "date": 1775560840008,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 94.44779387803788,
            "unit": "iter/sec",
            "range": "stddev: 0.00024741531649992925",
            "extra": "mean: 10.587859800000388 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10598.5420637514,
            "unit": "iter/sec",
            "range": "stddev: 0.000013209310059064573",
            "extra": "mean: 94.35260000714152 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 942.2605357905068,
            "unit": "iter/sec",
            "range": "stddev: 0.00009970827478691185",
            "extra": "mean: 1.061277600001631 msec\nrounds: 5"
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
          "id": "23fa11b179e43531d69336835e9d46dccfd47354",
          "message": "⚡ Bolt: Fix N+1 query in Deep Architectural Synthesis (#125)",
          "timestamp": "2026-04-08T09:14:50-05:00",
          "tree_id": "45241c0e87b9faefb6b62c10d36ed97e3a3d1cd5",
          "url": "https://github.com/sl4m3/ledgermind/commit/23fa11b179e43531d69336835e9d46dccfd47354"
        },
        "date": 1775657922669,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 100.529593921945,
            "unit": "iter/sec",
            "range": "stddev: 0.00008521812588317003",
            "extra": "mean: 9.947319600001947 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10013.75890575596,
            "unit": "iter/sec",
            "range": "stddev: 0.000015110870648007116",
            "extra": "mean: 99.8625999898195 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1006.6337161829681,
            "unit": "iter/sec",
            "range": "stddev: 0.00009436811814061813",
            "extra": "mean: 993.4100000066337 usec\nrounds: 5"
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
          "id": "5cd1bb0ee3f9ddd727cc68710fea2bc748156a8d",
          "message": "feat(cli): standardize output formatting with rich (#127)\n\n- Upgrade `check_project` to use `Console` for colored diagnostics.\n- Upgrade `show_stats` to use `Table` for structured metrics.\n- Add `rich` as a dependency in `pyproject.toml`.",
          "timestamp": "2026-04-09T08:43:40-05:00",
          "tree_id": "6109be5dfc2714ad19a5fd9a489e2501853838ca",
          "url": "https://github.com/sl4m3/ledgermind/commit/5cd1bb0ee3f9ddd727cc68710fea2bc748156a8d"
        },
        "date": 1775742445129,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 92.45344844058664,
            "unit": "iter/sec",
            "range": "stddev: 0.0005082403094802671",
            "extra": "mean: 10.81625420000023 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 12322.221154173354,
            "unit": "iter/sec",
            "range": "stddev: 0.000009568479614918009",
            "extra": "mean: 81.1542000008103 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1043.9285117734678,
            "unit": "iter/sec",
            "range": "stddev: 0.00009836310459668494",
            "extra": "mean: 957.9200000018773 usec\nrounds: 5"
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
          "id": "843e21d0964e6ddf02ba9ce0d3acd0def0dafec5",
          "message": "⚡ Bolt: [Performance Improvement] Memoize lifecycle weight calculation in search queries (#128)",
          "timestamp": "2026-04-10T06:27:51-05:00",
          "tree_id": "fee23987f6c1391a1c9e2c36607a57cfad9ef579",
          "url": "https://github.com/sl4m3/ledgermind/commit/843e21d0964e6ddf02ba9ce0d3acd0def0dafec5"
        },
        "date": 1775820692638,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 100.74263643362845,
            "unit": "iter/sec",
            "range": "stddev: 0.00004421859770504755",
            "extra": "mean: 9.926283799995872 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 9796.103893965557,
            "unit": "iter/sec",
            "range": "stddev: 0.000015754606993245853",
            "extra": "mean: 102.08139999576815 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1005.4206247549399,
            "unit": "iter/sec",
            "range": "stddev: 0.00008969685311497434",
            "extra": "mean: 994.6086000013564 usec\nrounds: 5"
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
          "id": "a9538cb3ea8ced2b3f7db7bed1f35a6731a6a0f1",
          "message": "feat(cli): enhance CLI feedback with rich console formatting and proper error logging (#129)",
          "timestamp": "2026-04-10T06:28:02-05:00",
          "tree_id": "49a4703984fa4a0867fb71c258159f7805061fce",
          "url": "https://github.com/sl4m3/ledgermind/commit/a9538cb3ea8ced2b3f7db7bed1f35a6731a6a0f1"
        },
        "date": 1775820701326,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 90.92550544262345,
            "unit": "iter/sec",
            "range": "stddev: 0.00019346945040945356",
            "extra": "mean: 10.998014199998352 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10310.95786778005,
            "unit": "iter/sec",
            "range": "stddev: 0.000031023259294154234",
            "extra": "mean: 96.98419999608632 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 936.1569073912693,
            "unit": "iter/sec",
            "range": "stddev: 0.00010528025116869417",
            "extra": "mean: 1.0681969999950525 msec\nrounds: 5"
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
          "id": "142fc9cc3c8b43ca5f298e3ca52795f39a97be7b",
          "message": "⚡ Bolt: Optimize search loop extraction and lifecycle multiplier lookup (#130)",
          "timestamp": "2026-04-12T08:04:39-05:00",
          "tree_id": "281ab7561860b23c4d24c34499bf35a6f50d0ea1",
          "url": "https://github.com/sl4m3/ledgermind/commit/142fc9cc3c8b43ca5f298e3ca52795f39a97be7b"
        },
        "date": 1775999298544,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 109.72575036212072,
            "unit": "iter/sec",
            "range": "stddev: 0.0001910727188919758",
            "extra": "mean: 9.113631000013811 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 12684.495994894647,
            "unit": "iter/sec",
            "range": "stddev: 0.000008735979043541251",
            "extra": "mean: 78.83639999590741 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1038.0214812214697,
            "unit": "iter/sec",
            "range": "stddev: 0.00008880598442417656",
            "extra": "mean: 963.3712000095329 usec\nrounds: 5"
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
          "id": "c05b986f37d82f82fb69217f5e215e9757a46302",
          "message": "🎨 Palette: Consistent CLI Visual Feedback and Logging (#131)",
          "timestamp": "2026-04-12T08:04:49-05:00",
          "tree_id": "7f068d19f77d2661228aa486bc57aeb377b2f2cf",
          "url": "https://github.com/sl4m3/ledgermind/commit/c05b986f37d82f82fb69217f5e215e9757a46302"
        },
        "date": 1775999312488,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 99.33131154397748,
            "unit": "iter/sec",
            "range": "stddev: 0.00013117137269691065",
            "extra": "mean: 10.067318999983854 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10271.580589263005,
            "unit": "iter/sec",
            "range": "stddev: 0.000014429710319897147",
            "extra": "mean: 97.35600001476996 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 995.1153766527509,
            "unit": "iter/sec",
            "range": "stddev: 0.00008889181566610254",
            "extra": "mean: 1.0049086000094576 msec\nrounds: 5"
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
            "email": "73834887+sl4m3@users.noreply.github.com",
            "name": "Stanislav",
            "username": "sl4m3"
          },
          "distinct": true,
          "id": "dc4b87257ae343fd0a2685b9ce387acba897af23",
          "message": "feat(benchmarks): comprehensive overhaul and real-world metrics\n\n- Update README with new comparative benchmarks (LoCoMo/LongMemEval)\n- Enhance benchmark CLI with 'rich' progress bars and better visualization\n- Improve data loading performance and scale vector search tests to 100k\n- Fix git audit provider locale issues for consistent error parsing\n- Cleanup temporary patch files and optimize test runner\n- Add namespace defaults to integration bridge",
          "timestamp": "2026-04-12T15:19:43-05:00",
          "tree_id": "25e53e697fac6089d21351463d0061e29db37d19",
          "url": "https://github.com/sl4m3/ledgermind/commit/dc4b87257ae343fd0a2685b9ce387acba897af23"
        },
        "date": 1776025396252,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 99.41621407277863,
            "unit": "iter/sec",
            "range": "stddev: 0.00023162384540548463",
            "extra": "mean: 10.058721399991555 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11449.900959557706,
            "unit": "iter/sec",
            "range": "stddev: 0.000010905981800735319",
            "extra": "mean: 87.3369999908391 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1021.6270268572098,
            "unit": "iter/sec",
            "range": "stddev: 0.00009229627697180755",
            "extra": "mean: 978.8307999997413 usec\nrounds: 5"
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
            "email": "73834887+sl4m3@users.noreply.github.com",
            "name": "Stanislav",
            "username": "sl4m3"
          },
          "distinct": true,
          "id": "19208b208981e2660c124a3d3bf29c6fd97e1a51",
          "message": "release: v3.3.6 (performance and security update)",
          "timestamp": "2026-04-12T20:47:28-05:00",
          "tree_id": "52b98f7571fd3ece12504fc1b37244e7ea4ef674",
          "url": "https://github.com/sl4m3/ledgermind/commit/19208b208981e2660c124a3d3bf29c6fd97e1a51"
        },
        "date": 1776045083672,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 94.5908022703281,
            "unit": "iter/sec",
            "range": "stddev: 0.0003740523633448491",
            "extra": "mean: 10.571852400005355 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 9852.100271461133,
            "unit": "iter/sec",
            "range": "stddev: 0.000025123218360079045",
            "extra": "mean: 101.50119999252638 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 933.1984799369988,
            "unit": "iter/sec",
            "range": "stddev: 0.00006216041927335127",
            "extra": "mean: 1.0715833999938695 msec\nrounds: 5"
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
            "email": "73834887+sl4m3@users.noreply.github.com",
            "name": "Stanislav",
            "username": "sl4m3"
          },
          "distinct": true,
          "id": "cc8b5dbdda611d26cc932354485a2dee82f05c19",
          "message": "chore: finalize v3.3.6 release (formatting and version consistency)",
          "timestamp": "2026-04-13T07:16:22-05:00",
          "tree_id": "54d69810ec60cbbad73084da2410292efb44727d",
          "url": "https://github.com/sl4m3/ledgermind/commit/cc8b5dbdda611d26cc932354485a2dee82f05c19"
        },
        "date": 1776082807285,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 82.97361092330353,
            "unit": "iter/sec",
            "range": "stddev: 0.0003666758076903862",
            "extra": "mean: 12.052024600018285 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11147.576069829745,
            "unit": "iter/sec",
            "range": "stddev: 0.00001238263248345313",
            "extra": "mean: 89.7056000098928 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1003.4472426619477,
            "unit": "iter/sec",
            "range": "stddev: 0.00010648435054428088",
            "extra": "mean: 996.5645999955087 usec\nrounds: 5"
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
            "email": "73834887+sl4m3@users.noreply.github.com",
            "name": "Stanislav",
            "username": "sl4m3"
          },
          "distinct": true,
          "id": "e224c4a6078473bcf6b3aa46301b70a3117177f5",
          "message": "feat(vscode): implement dual-hook mechanism and enhanced agent integration",
          "timestamp": "2026-04-13T16:22:11-05:00",
          "tree_id": "47acfb7b16f65034dd14efc558f6eea8c4887c1b",
          "url": "https://github.com/sl4m3/ledgermind/commit/e224c4a6078473bcf6b3aa46301b70a3117177f5"
        },
        "date": 1776115555043,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 96.27273186931008,
            "unit": "iter/sec",
            "range": "stddev: 0.00008278916365401784",
            "extra": "mean: 10.387157200000274 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 12566.097672559332,
            "unit": "iter/sec",
            "range": "stddev: 0.000012520795807859967",
            "extra": "mean: 79.57920000762897 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1080.071768608986,
            "unit": "iter/sec",
            "range": "stddev: 0.00009244501958176969",
            "extra": "mean: 925.8643999999094 usec\nrounds: 5"
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
          "id": "6b9437b0a7dd4d55a865b3324321e06f1a6d7d4f",
          "message": "⚡ Bolt: Eliminate redundant database query in search (#133)",
          "timestamp": "2026-04-14T14:28:47+03:00",
          "tree_id": "f47a4101376b772a950ac78652fae8a74d6f9a1a",
          "url": "https://github.com/sl4m3/ledgermind/commit/6b9437b0a7dd4d55a865b3324321e06f1a6d7d4f"
        },
        "date": 1776166352885,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 93.86549915012944,
            "unit": "iter/sec",
            "range": "stddev: 0.0001022245014426764",
            "extra": "mean: 10.653541599992877 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11188.610890038726,
            "unit": "iter/sec",
            "range": "stddev: 0.000013917073915948197",
            "extra": "mean: 89.37659999332936 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1129.0611765902177,
            "unit": "iter/sec",
            "range": "stddev: 0.00009972278493187855",
            "extra": "mean: 885.6916000070214 usec\nrounds: 5"
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
          "id": "6d12c0248adf205e40d192038d9ff5a2ea9aacd6",
          "message": "🎨 Palette: [UX improvement] Consistent CLI visual feedback in settings (#134)",
          "timestamp": "2026-04-14T14:28:56+03:00",
          "tree_id": "bc75041e0e6e8cbda396e1d0569dd101a09867b6",
          "url": "https://github.com/sl4m3/ledgermind/commit/6d12c0248adf205e40d192038d9ff5a2ea9aacd6"
        },
        "date": 1776166362352,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 72.65480180814987,
            "unit": "iter/sec",
            "range": "stddev: 0.004236612552408976",
            "extra": "mean: 13.76371520000248 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10180.085718260008,
            "unit": "iter/sec",
            "range": "stddev: 0.000021976159458068553",
            "extra": "mean: 98.23099998129692 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1043.3536390856452,
            "unit": "iter/sec",
            "range": "stddev: 0.0000950821146790289",
            "extra": "mean: 958.4477999965202 usec\nrounds: 5"
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
          "id": "660481f04877a8d4cd93c560c2c2e1c687e3fb3b",
          "message": "⚡ Bolt: Batch database updates in search hot path (#135)",
          "timestamp": "2026-04-15T16:24:12+03:00",
          "tree_id": "4128202648a6b931bfb2d2d76bb6fcc57e61062c",
          "url": "https://github.com/sl4m3/ledgermind/commit/660481f04877a8d4cd93c560c2c2e1c687e3fb3b"
        },
        "date": 1776259675346,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 97.0691334134594,
            "unit": "iter/sec",
            "range": "stddev: 0.00042254306355807595",
            "extra": "mean: 10.30193599999052 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11315.929434090322,
            "unit": "iter/sec",
            "range": "stddev: 0.000010594014671035415",
            "extra": "mean: 88.37099999823295 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1274.9293306558557,
            "unit": "iter/sec",
            "range": "stddev: 0.000038795800447199446",
            "extra": "mean: 784.3572000069798 usec\nrounds: 5"
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
          "id": "bfcc30877c7919e65b8585416defeac6e294e2ba",
          "message": "feat(ux): add missing accessibility states for background watchers (#136)",
          "timestamp": "2026-04-15T16:24:23+03:00",
          "tree_id": "22e51e0be1ca0383e103c3774be59eae28b03869",
          "url": "https://github.com/sl4m3/ledgermind/commit/bfcc30877c7919e65b8585416defeac6e294e2ba"
        },
        "date": 1776259685199,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 86.43422004056815,
            "unit": "iter/sec",
            "range": "stddev: 0.0006315753549682146",
            "extra": "mean: 11.569491800014475 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 12674.174849819281,
            "unit": "iter/sec",
            "range": "stddev: 0.00001077483989270536",
            "extra": "mean: 78.90059998771903 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1324.2135627741532,
            "unit": "iter/sec",
            "range": "stddev: 0.00005589162881061604",
            "extra": "mean: 755.1652000188369 usec\nrounds: 5"
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
          "id": "d3fcae25164e41a9abc29c68c5e6e92ccc0b9e3a",
          "message": "⚡ Bolt: O(N) max/sort optimizations (#137)",
          "timestamp": "2026-04-16T17:07:37+03:00",
          "tree_id": "e2a09524ccb3932dfca7c37c42294f69140c1be8",
          "url": "https://github.com/sl4m3/ledgermind/commit/d3fcae25164e41a9abc29c68c5e6e92ccc0b9e3a"
        },
        "date": 1776348683345,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 93.3381709885674,
            "unit": "iter/sec",
            "range": "stddev: 0.00021051755659190824",
            "extra": "mean: 10.713730399993437 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 9913.711058242727,
            "unit": "iter/sec",
            "range": "stddev: 0.00002308706317009947",
            "extra": "mean: 100.87040000712477 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1269.7116383325022,
            "unit": "iter/sec",
            "range": "stddev: 0.00003315305799102615",
            "extra": "mean: 787.580399997978 usec\nrounds: 5"
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
          "id": "9a87f2a8148bae66824d88b638a8de75468eac17",
          "message": "🎨 Palette: Improve error state visibility and dismissal (#138)\n\n- Updated VS Code status bar error handling to be dismissable\n- Added `setError(true)` to file watcher errors\n- Registered command correctly down the flow so it clears error.\n- Recorded learning in .jules/palette.md",
          "timestamp": "2026-04-16T17:07:46+03:00",
          "tree_id": "02da7fcf522088dac562c36d1883806bd18bf7bc",
          "url": "https://github.com/sl4m3/ledgermind/commit/9a87f2a8148bae66824d88b638a8de75468eac17"
        },
        "date": 1776348695865,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 96.41335939765082,
            "unit": "iter/sec",
            "range": "stddev: 0.00009832026322479521",
            "extra": "mean: 10.37200659999371 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11482.45366478087,
            "unit": "iter/sec",
            "range": "stddev: 0.000016158556795082348",
            "extra": "mean: 87.08939998314236 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1370.3236677062905,
            "unit": "iter/sec",
            "range": "stddev: 0.000020800964526803472",
            "extra": "mean: 729.7546000017974 usec\nrounds: 5"
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
          "id": "74b3ac48036e73588a99d957ab49819797f0f09d",
          "message": "Replace lambda functions with C-optimized accessors for faster sorting (#139)",
          "timestamp": "2026-04-18T16:18:07+03:00",
          "tree_id": "72df7400cde301e54c63c715a8718a92c0de9a96",
          "url": "https://github.com/sl4m3/ledgermind/commit/74b3ac48036e73588a99d957ab49819797f0f09d"
        },
        "date": 1776518502156,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 95.82447164583395,
            "unit": "iter/sec",
            "range": "stddev: 0.00014613195278243864",
            "extra": "mean: 10.435747600007517 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11488.891390295841,
            "unit": "iter/sec",
            "range": "stddev: 0.000013738632768369677",
            "extra": "mean: 87.04060000468417 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1375.0021312554632,
            "unit": "iter/sec",
            "range": "stddev: 0.000024496895119725734",
            "extra": "mean: 727.2715999988577 usec\nrounds: 5"
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
          "id": "29610b31e55c5d1a9fb3fe1aee738005bf0ffe13",
          "message": "Fix insecure deserialization in VectorStore (#140)",
          "timestamp": "2026-04-18T16:18:23+03:00",
          "tree_id": "bf310924c8ec2276aaf92cc7c5c50538ecdd1714",
          "url": "https://github.com/sl4m3/ledgermind/commit/29610b31e55c5d1a9fb3fe1aee738005bf0ffe13"
        },
        "date": 1776518520106,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 97.77650937747714,
            "unit": "iter/sec",
            "range": "stddev: 0.0002683649898927524",
            "extra": "mean: 10.227405399996314 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11379.930358264079,
            "unit": "iter/sec",
            "range": "stddev: 0.00001213640516260579",
            "extra": "mean: 87.87399997345346 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1313.3601030848586,
            "unit": "iter/sec",
            "range": "stddev: 0.000030642042828868",
            "extra": "mean: 761.4058000172008 usec\nrounds: 5"
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
          "id": "76d96ee3b77ad40f6a88e68a620acecedb1a4e58",
          "message": "🎨 Palette: Fix concurrent loading states for status bar item (#141)",
          "timestamp": "2026-04-18T16:18:32+03:00",
          "tree_id": "7b1808db32d93ec9ed54ebb4c815ac860055936f",
          "url": "https://github.com/sl4m3/ledgermind/commit/76d96ee3b77ad40f6a88e68a620acecedb1a4e58"
        },
        "date": 1776518536856,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 95.49060878502459,
            "unit": "iter/sec",
            "range": "stddev: 0.000596712106890585",
            "extra": "mean: 10.47223400000803 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11541.373515637135,
            "unit": "iter/sec",
            "range": "stddev: 0.000009404367289505772",
            "extra": "mean: 86.64480000106778 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1304.048235191047,
            "unit": "iter/sec",
            "range": "stddev: 0.000033148341210888335",
            "extra": "mean: 766.8427999931282 usec\nrounds: 5"
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
          "id": "093815d3e751fe539d37d6ffc4fb49c3efd07cd9",
          "message": "Optimize python lambda sort bottlenecks with dict.get and itemgetter (#142)",
          "timestamp": "2026-04-19T14:17:24+03:00",
          "tree_id": "082a319c81b47fcb3594a68e6fa88bbceec13ec0",
          "url": "https://github.com/sl4m3/ledgermind/commit/093815d3e751fe539d37d6ffc4fb49c3efd07cd9"
        },
        "date": 1776597654730,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 95.41419713242779,
            "unit": "iter/sec",
            "range": "stddev: 0.00008525557544844101",
            "extra": "mean: 10.480620600014845 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 11387.550221511285,
            "unit": "iter/sec",
            "range": "stddev: 0.000015492688774239748",
            "extra": "mean: 87.8151999813781 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1378.3525323982815,
            "unit": "iter/sec",
            "range": "stddev: 0.000032706691087297443",
            "extra": "mean: 725.5038000039349 usec\nrounds: 5"
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
          "id": "cc73fa782e7f199e84b894074ba91df96b6cb067",
          "message": "🎨 Palette: Fix VS Code concurrent loading states clearing errors (#143)",
          "timestamp": "2026-04-19T14:17:33+03:00",
          "tree_id": "54d69d88b4150660b46d1e962467727337f2b8a5",
          "url": "https://github.com/sl4m3/ledgermind/commit/cc73fa782e7f199e84b894074ba91df96b6cb067"
        },
        "date": 1776597677574,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_record_decision",
            "value": 99.84254032651847,
            "unit": "iter/sec",
            "range": "stddev: 0.00008117826932692774",
            "extra": "mean: 10.015770799998336 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_fast_path",
            "value": 10185.705787013838,
            "unit": "iter/sec",
            "range": "stddev: 0.000014069587031401168",
            "extra": "mean: 98.17680000878681 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 1336.5956961022096,
            "unit": "iter/sec",
            "range": "stddev: 0.000020300638770199118",
            "extra": "mean: 748.1694000034622 usec\nrounds: 5"
          }
        ]
      }
    ]
  }
}