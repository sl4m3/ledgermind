window.BENCHMARK_DATA = {
  "lastUpdate": 1772411755755,
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
          "id": "577b97dea7588dc5e09af1ea64dcfc1f610e6775",
          "message": "docs: refactor documentation filenames to lowercase and update README structure\n\n- Renamed documentation files from uppercase to lowercase for consistency (e.g., ARCHITECTURE.md -> architecture.md).\n- Restructured README.md with clearer sections on 'What is LedgerMind' and core capabilities.\n- Updated .gitignore to include .jules/ and audit/ directories.\n- Refined tutorials and reference materials.",
          "timestamp": "2026-03-01T17:39:25+03:00",
          "tree_id": "5ca07b96711f320450914cc2d640943c4de19a04",
          "url": "https://github.com/sl4m3/ledgermind/commit/577b97dea7588dc5e09af1ea64dcfc1f610e6775"
        },
        "date": 1772376103215,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 69.00863097844604,
            "unit": "iter/sec",
            "range": "stddev: 0.0004043838834699617",
            "extra": "mean: 14.490941000008206 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 19155.91381191575,
            "unit": "iter/sec",
            "range": "stddev: 0.000008348954403226818",
            "extra": "mean: 52.203200004896644 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 607.3210364504671,
            "unit": "iter/sec",
            "range": "stddev: 0.00012396218433302248",
            "extra": "mean: 1.6465756000229703 msec\nrounds: 5"
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
          "id": "5f5c1d4f84d60213c21c5f9f7dc8ccbf0720609f",
          "message": "🛡️ Sentinel: [MEDIUM] Fix API Key Timing Attack Vulnerability (#41)\n\n* Fix API key timing attack vulnerability in gateway.py and server.py\n\nReplaced standard string equality operators with `hmac.compare_digest`\nfor comparing API keys to prevent timing attacks. Handled optional API\nkey configurations gracefully to prevent regressions. Added sentinel\njournal entry.\n\n* Fix CI test failure in test_multi_process_locking\n\nIncreased `sqlite3` connection timeout to 60.0s and `PRAGMA busy_timeout` to\n60000ms in `SemanticMetaStore` to prevent \"database is locked\" OperationalErrors\nduring highly concurrent multi-process tests in CI pipelines.",
          "timestamp": "2026-03-01T17:42:18+03:00",
          "tree_id": "810fbdac71c5ce9a605784e10f2bda431269cf55",
          "url": "https://github.com/sl4m3/ledgermind/commit/5f5c1d4f84d60213c21c5f9f7dc8ccbf0720609f"
        },
        "date": 1772376268834,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 71.16315725087168,
            "unit": "iter/sec",
            "range": "stddev: 0.0002664506168400499",
            "extra": "mean: 14.052215199990314 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 18461.28852297597,
            "unit": "iter/sec",
            "range": "stddev: 0.000010059037673853083",
            "extra": "mean: 54.16740000327991 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 614.9063128856939,
            "unit": "iter/sec",
            "range": "stddev: 0.00009503043982287246",
            "extra": "mean: 1.6262639999695239 msec\nrounds: 5"
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
          "id": "58e7de0c107f23980f8e75dad369c76fd3431772",
          "message": "⚡ Bolt: Eliminate N+1 query in grounding link retrieval (#40)\n\nOptimized `Memory.process_event` by replacing individual looped queries\nto `EpisodicStore.get_linked_event_ids` with a batched query method\n`EpisodicStore.get_linked_event_ids_batch`. The new method chunks inputs\nto avoid SQLite parameter limits, fetching all links for superseded\nitems efficiently.",
          "timestamp": "2026-03-01T17:42:05+03:00",
          "tree_id": "2b410c1d0a27c1bc299fa55e79bf99819b785e46",
          "url": "https://github.com/sl4m3/ledgermind/commit/58e7de0c107f23980f8e75dad369c76fd3431772"
        },
        "date": 1772376271299,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 69.12289720715954,
            "unit": "iter/sec",
            "range": "stddev: 0.00043167179552655187",
            "extra": "mean: 14.466986200000065 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 19594.472789796037,
            "unit": "iter/sec",
            "range": "stddev: 0.000008109303333147838",
            "extra": "mean: 51.03480000343552 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 600.8414423913571,
            "unit": "iter/sec",
            "range": "stddev: 0.0001241947880915225",
            "extra": "mean: 1.6643325999950775 msec\nrounds: 5"
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
          "id": "1d75abde86236b000f7e984146479c7484f0b6be",
          "message": "feat: Add accessibilityInformation to VS Code extension StatusBarItem (#42)\n\nAdded `accessibilityInformation` (with label and role) to the `StatusBarItem` in the LedgerMind VS Code extension. The label updates dynamically to announce the \"busy/syncing\" state, improving the experience for users relying on screen readers.",
          "timestamp": "2026-03-01T17:42:31+03:00",
          "tree_id": "5d5e781a23e10cd0bbee610bee2efedd4ce51f8a",
          "url": "https://github.com/sl4m3/ledgermind/commit/1d75abde86236b000f7e984146479c7484f0b6be"
        },
        "date": 1772376292009,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 66.6075875127418,
            "unit": "iter/sec",
            "range": "stddev: 0.0006039401706135277",
            "extra": "mean: 15.013304600000765 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 19406.924388410345,
            "unit": "iter/sec",
            "range": "stddev: 0.00000838751939917262",
            "extra": "mean: 51.528000005873764 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 610.9890287154011,
            "unit": "iter/sec",
            "range": "stddev: 0.00011461889078198953",
            "extra": "mean: 1.636690599997337 msec\nrounds: 5"
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
          "id": "e63f887ec4c4d59fc13edddd41fa9858b2cd213a",
          "message": "docs: remove .jules/ directory from tracking (added to .gitignore)",
          "timestamp": "2026-03-01T17:49:21+03:00",
          "tree_id": "5912fad5e5214bba988bfc116d57b87fe798121c",
          "url": "https://github.com/sl4m3/ledgermind/commit/e63f887ec4c4d59fc13edddd41fa9858b2cd213a"
        },
        "date": 1772376722791,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 54.71663823424179,
            "unit": "iter/sec",
            "range": "stddev: 0.0068873047011242935",
            "extra": "mean: 18.27597660000606 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 19009.816668401138,
            "unit": "iter/sec",
            "range": "stddev: 0.000007876034964902532",
            "extra": "mean: 52.604400002564944 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 603.2480807056764,
            "unit": "iter/sec",
            "range": "stddev: 0.00013564811492775876",
            "extra": "mean: 1.657692800000632 msec\nrounds: 5"
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
          "id": "24377be3efe0c4a9de6b7f671fcb45a6518294aa",
          "message": "security: fix SQL injection and harden subprocess/exception handling\n\n- Fixed critical SQL injection vulnerability in EpisodicStore (Bandit B608) by using constant SQL templates and parameterized queries.\n- Audited and marked all subprocess calls with # nosec B603 B607 to ensure path and argument safety.\n- Refined empty 'except: pass' blocks across the core reasoning and storage layers to improve debuggability and satisfy Bandit B110.\n- Resolved multiple low-severity security warnings identified in the project audit.",
          "timestamp": "2026-03-01T18:08:05+03:00",
          "tree_id": "938da61593f708bde2ef2973b5652b16d7680f73",
          "url": "https://github.com/sl4m3/ledgermind/commit/24377be3efe0c4a9de6b7f671fcb45a6518294aa"
        },
        "date": 1772377835508,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 65.22388136412351,
            "unit": "iter/sec",
            "range": "stddev: 0.00045581513271142576",
            "extra": "mean: 15.331807600000502 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 18895.447708563857,
            "unit": "iter/sec",
            "range": "stddev: 0.000007103787663739774",
            "extra": "mean: 52.92280000048777 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 582.9041216008924,
            "unit": "iter/sec",
            "range": "stddev: 0.00010179062131475244",
            "extra": "mean: 1.7155479999928502 msec\nrounds: 5"
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
          "id": "3c9e2dd2d722f93c114e6b4979b186fd27f187dd",
          "message": "security: fix TOCTOU path traversal vulnerability in SemanticStore\n\n- Replaced naive string-based path validation with robust canonical path resolution using pathlib.Path.resolve().\n- Explicitly blocked null bytes, absolute paths, and home directory expansion before resolution.\n- Updated update_decision to correctly use the validated and canonicalized file identifier.",
          "timestamp": "2026-03-01T18:15:18+03:00",
          "tree_id": "3c34912bd695a2bbb13ed617412efa208f08ccdc",
          "url": "https://github.com/sl4m3/ledgermind/commit/3c9e2dd2d722f93c114e6b4979b186fd27f187dd"
        },
        "date": 1772378259328,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 68.38287346563264,
            "unit": "iter/sec",
            "range": "stddev: 0.0005913005577739264",
            "extra": "mean: 14.623544599987781 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 17039.490724127892,
            "unit": "iter/sec",
            "range": "stddev: 0.000021795865110252438",
            "extra": "mean: 58.68719999853056 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 254.92686963816925,
            "unit": "iter/sec",
            "range": "stddev: 0.00013516996056392623",
            "extra": "mean: 3.9226936000090977 msec\nrounds: 5"
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
          "id": "f31021cc057ed53980a5ed8159acca3d58aa7d40",
          "message": "feat: add minimal CI pipeline with security scanning",
          "timestamp": "2026-03-01T18:30:31+03:00",
          "tree_id": "7fad707225d53156a84fcdf846e00fc6ee1dd8a3",
          "url": "https://github.com/sl4m3/ledgermind/commit/f31021cc057ed53980a5ed8159acca3d58aa7d40"
        },
        "date": 1772379726519,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 68.75647385174112,
            "unit": "iter/sec",
            "range": "stddev: 0.00017302596117762056",
            "extra": "mean: 14.544084999999995 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 17933.93853436006,
            "unit": "iter/sec",
            "range": "stddev: 0.000009094774201981036",
            "extra": "mean: 55.76020002990845 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 252.9829984295328,
            "unit": "iter/sec",
            "range": "stddev: 0.00011389014246293347",
            "extra": "mean: 3.952834799997617 msec\nrounds: 5"
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
          "id": "02ebd2a77397e7462d37ff84596c59d3479defd9",
          "message": "ci: fix pipeline failures by updating actions and adding missing dependencies\n\n- Updated setup-python to v5, upload-artifact to v4, and codecov to v4 to resolve deprecation failures.\n- Added explicit installation of 'pytest-cov' in the test job.\n- Switched to newer versions of core GitHub Actions for better reliability.",
          "timestamp": "2026-03-01T19:04:22+03:00",
          "tree_id": "a30218e37851f863159ede13414a8230590fcbe8",
          "url": "https://github.com/sl4m3/ledgermind/commit/02ebd2a77397e7462d37ff84596c59d3479defd9"
        },
        "date": 1772381208726,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 65.88622326845405,
            "unit": "iter/sec",
            "range": "stddev: 0.0012671447401160691",
            "extra": "mean: 15.177679800001442 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 16685.242907519787,
            "unit": "iter/sec",
            "range": "stddev: 0.000011262928030873784",
            "extra": "mean: 59.93319998651714 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 620.5605871312181,
            "unit": "iter/sec",
            "range": "stddev: 0.00009628831648215217",
            "extra": "mean: 1.6114461999961804 msec\nrounds: 5"
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
          "id": "957f979c87ca099c5aaf5bbed956a981aea48976",
          "message": "fix(core): resolve SQLite 'database is locked' errors in concurrent environments\n\n- Switched to BEGIN IMMEDIATE for manual transactions to ensure write lock acquisition at start.\n- Implemented _execute_with_retry with exponential backoff for write operations.\n- Set PRAGMA synchronous=NORMAL for better reliability in WAL mode.\n- Resolves CI failures in multi-process concurrency tests.",
          "timestamp": "2026-03-01T19:16:02+03:00",
          "tree_id": "44fddf75e660856c075e30b7db1a0cb4a4071cd1",
          "url": "https://github.com/sl4m3/ledgermind/commit/957f979c87ca099c5aaf5bbed956a981aea48976"
        },
        "date": 1772381913558,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 68.1436465889567,
            "unit": "iter/sec",
            "range": "stddev: 0.0004157007995714561",
            "extra": "mean: 14.674882399998523 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 18944.273525304066,
            "unit": "iter/sec",
            "range": "stddev: 0.0000072659514374813",
            "extra": "mean: 52.78639999914958 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 627.6532471899774,
            "unit": "iter/sec",
            "range": "stddev: 0.0001280498076440043",
            "extra": "mean: 1.593236399997977 msec\nrounds: 5"
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
          "id": "47f53ccc978336a96feea7785be45bc815611c9f",
          "message": "release: v3.1.1 - Critical Security Fixes and Performance Restoration\n\n- Bumped version to 3.1.1.\n- Addressed SQLi, Path Traversal, and Race Condition vulnerabilities.\n- Restored search throughput to 690+ ops/s via path validation caching.\n- Stabilized concurrent SQLite operations with retries and BEGIN IMMEDIATE.\n- Created detailed changelog and updated documentation index.",
          "timestamp": "2026-03-01T19:33:47+03:00",
          "tree_id": "e992a26d45dbe6d28d9aee408c4c635606b7761b",
          "url": "https://github.com/sl4m3/ledgermind/commit/47f53ccc978336a96feea7785be45bc815611c9f"
        },
        "date": 1772382982494,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 70.47174731975959,
            "unit": "iter/sec",
            "range": "stddev: 0.0003346891934354365",
            "extra": "mean: 14.19008380000264 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 20202.673220061588,
            "unit": "iter/sec",
            "range": "stddev: 0.000008280082023794546",
            "extra": "mean: 49.49839999426331 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 620.9069811803517,
            "unit": "iter/sec",
            "range": "stddev: 0.0001335571314106821",
            "extra": "mean: 1.610547199999246 msec\nrounds: 5"
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
          "id": "0f144ced3c6ef0d8fbfd0f1f38ef96bd0e81d472",
          "message": "release: v3.1.2 - Production Hardening and Monitoring\n\n- Implemented unified error handling with Result pattern.\n- Added SQLAlchemy connection pooling for episodic storage.\n- Integrated comprehensive health check endpoints.\n- Hardened input sanitization for memory events.\n- Updated documentation and version to 3.1.2.",
          "timestamp": "2026-03-01T20:38:47+03:00",
          "tree_id": "20e9004a05dd4357d2ee656dd4ae242a795011d6",
          "url": "https://github.com/sl4m3/ledgermind/commit/0f144ced3c6ef0d8fbfd0f1f38ef96bd0e81d472"
        },
        "date": 1772386863752,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 76.13874129349657,
            "unit": "iter/sec",
            "range": "stddev: 0.000539220368232504",
            "extra": "mean: 13.133918200003336 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 17320.39615463783,
            "unit": "iter/sec",
            "range": "stddev: 0.000015048972659834412",
            "extra": "mean: 57.73539999154309 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 786.0196655835084,
            "unit": "iter/sec",
            "range": "stddev: 0.00011863712907740196",
            "extra": "mean: 1.2722327999995287 msec\nrounds: 5"
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
          "id": "1055480b0704d35f5ebea05d0764c054aa019545",
          "message": "feat(reasoning): unify procedural and behavioral hypothesis lifecycles\n\n- Extended ProposalContent in schemas.py with phase, vitality, stability_score, and frequency.\n- Updated ReflectionEngine to inject decision_id into proposals, allowing them to be processed by LifecycleEngine as DecisionStreams.\n- Fixed old tests that failed to unpack the new Result type from EpisodicStore.\n- Procedural knowledge (instructions) now properly evolves from PATTERN to EMERGENT and decays if unused.",
          "timestamp": "2026-03-01T22:37:56+03:00",
          "tree_id": "f0d47bfba207b290a5246180a9646c2849c26413",
          "url": "https://github.com/sl4m3/ledgermind/commit/1055480b0704d35f5ebea05d0764c054aa019545"
        },
        "date": 1772394640308,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 75.63081964978112,
            "unit": "iter/sec",
            "range": "stddev: 0.0005310005028707316",
            "extra": "mean: 13.222122999997055 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 19684.806869451404,
            "unit": "iter/sec",
            "range": "stddev: 0.000009039292628933825",
            "extra": "mean: 50.800600007505636 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 791.7910900397753,
            "unit": "iter/sec",
            "range": "stddev: 0.00012495205786034334",
            "extra": "mean: 1.2629593999974986 msec\nrounds: 5"
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
          "id": "89f36dc2b7494188c372d9500e254b498cd54dad",
          "message": "fix(cli): prevent duplicate prompt recording by relying on Stop hook sync",
          "timestamp": "2026-03-02T03:29:31+03:00",
          "tree_id": "8d687eefa3e4a6623fbaa6e4440192caac3bac7b",
          "url": "https://github.com/sl4m3/ledgermind/commit/89f36dc2b7494188c372d9500e254b498cd54dad"
        },
        "date": 1772411754852,
        "tool": "pytest",
        "benches": [
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_record_decision",
            "value": 71.53956199307034,
            "unit": "iter/sec",
            "range": "stddev: 0.001630778475136074",
            "extra": "mean: 13.978279599990628 msec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_fast_path",
            "value": 20088.792467387342,
            "unit": "iter/sec",
            "range": "stddev: 0.00000880896824162637",
            "extra": "mean: 49.778999988348005 usec\nrounds: 5"
          },
          {
            "name": "tests/core/performance/test_bench_ops.py::test_benchmark_search_hybrid_rrf",
            "value": 788.6588336034898,
            "unit": "iter/sec",
            "range": "stddev: 0.00012751812006865895",
            "extra": "mean: 1.2679753999975674 msec\nrounds: 5"
          }
        ]
      }
    ]
  }
}