window.BENCHMARK_DATA = {
  "lastUpdate": 1775390782102,
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
      }
    ]
  }
}