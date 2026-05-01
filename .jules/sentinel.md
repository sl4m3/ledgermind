## 2024-05-24 - Missing authentication on admin endpoint in fastMCP handler
**Vulnerability:** The `handle_accept_proposal` tool handler in the MCP server lacked the `self._validate_auth()` check that was present in all other handlers (record, supersede, search). This allowed unauthenticated actors to bypass authorization and accept arbitrary proposals.
**Learning:** Even when using higher-level abstractions like FastMCP, if authentication logic is implemented via manual checks within handlers instead of middleware or decorators, it is easy to forget the check when adding new endpoints or tools.
**Prevention:** Consider refactoring authentication checks into decorators (e.g., `@require_auth`) or using standard FastMCP middleware instead of manually calling `self._validate_auth()` inside every method to enforce a secure-by-default posture.
## 2024-05-24 - [Bandit B603 Subprocess Call with Untrusted Input Fix]
**Vulnerability:** Subprocess calls executed using string literals representing binaries without absolute paths are prone to execution of unintended executables due to modified PATH environments (Command Injection / Hijacking risk, detected by Bandit B603).
**Learning:** Hardcoding tool names like "gemini" and "claude" directly in `subprocess.run` argument lists creates a security gap. We must resolve their absolute paths first and explicitly handle cases when they are missing.
**Prevention:** Always use `shutil.which('binary_name')` to resolve the absolute executable path before executing it with `subprocess.run`, raise a `FileNotFoundError` if missing, pass arguments safely as a list, and append `# nosec B603` when verifying and confirming the code is secure against this specific vulnerability.
## 2024-05-30 - Fix insecure subprocess execution
**Vulnerability:** Found `subprocess.Popen` and `subprocess.run` executing external commands like `gemini` and `claude` without explicitly resolving their full path, creating a CWE-78 (insecure subprocess execution) B603 bandit vulnerability.
**Learning:** Hardcoded binary names like `gemini` and `claude` passed to `subprocess.run/Popen` are susceptible to local privilege escalation or malicious binary interception if the `PATH` environment variable is manipulated or insecure.
**Prevention:** Always use `shutil.which('binary_name')` to reliably determine the absolute path of an executable before executing it via `subprocess.run` or `subprocess.Popen`. Add `if not path:` checks to explicitly handle when the executable is missing and raise `FileNotFoundError`. Finally, apply `# nosec B603` to properly inform security scanners like Bandit that the execution is secured.
## 2024-05-24 - Unresolved paths in subprocess execution
**Vulnerability:** Unresolved paths in subprocess execution (B603) via command injection risk.
**Learning:** Executing subprocesses via string or unverified list paths exposes the system to command injection.
**Prevention:** Always use `shutil.which` to resolve executable paths and suppress false positives with `# nosec B603`.
## 2024-05-18 - [Bandit B603: Secure Subprocess Execution]
**Vulnerability:** Subprocess calls without absolute paths risk executing malicious shadowing binaries.
**Learning:** Using `shutil.which()` correctly resolves to absolute paths before execution and explicitly handling `FileNotFoundError` makes it safe, satisfying B603.
**Prevention:** Always wrap executable lookups with `shutil.which`, check its existence, and append `# nosec B603` inline on the `subprocess.run` or `subprocess.Popen` line.
## 2024-05-18 - [Bandit B603: sys.executable False Positive]
**Vulnerability:** Bandit flags all `subprocess.Popen` calls with untrusted input as B603, even when the command array begins with a safe, absolute path like `sys.executable`.
**Learning:** `sys.executable` reliably points to the exact Python interpreter currently running, which is critical for virtual environments and is already an absolute, secure path. Replacing it with `shutil.which("python")` introduces path-hijacking vulnerabilities and functional regressions.
**Prevention:** When using `sys.executable` in a command array passed to `subprocess.run` or `subprocess.Popen`, it is secure by default. Simply append `# nosec B603` to the call to suppress the false positive in Bandit.
## 2024-05-24 - Missing authentication on admin endpoint in fastMCP handler
**Vulnerability:** Direct MCP tools like `forget_memory` and `export_memory_bundle` in `LedgerMindTools` lacked the `self.server._validate_auth()` check, allowing unauthenticated API access.
**Learning:** Even when using higher-level abstractions like FastMCP, if authentication logic is implemented via manual checks within handlers instead of middleware or decorators, it is easy to forget the check when adding new endpoints or tools.
**Prevention:** Consider refactoring authentication checks into decorators (e.g., `@require_auth`) or using standard FastMCP middleware instead of manually calling `self._validate_auth()` inside every method to enforce a secure-by-default posture.
## 2025-01-20 - [Fix Path Hijacking in GitAuditProvider]
**Vulnerability:** Insecure Subprocess Call (Path Hijacking risk via unqualified `git` command)
**Learning:** Subprocess calls without absolute paths allow malicious binaries injected into the PATH to be executed.
**Prevention:** Always use `shutil.which` to resolve absolute paths of binaries and explicitly handle execution failure if the executable cannot be found before executing `subprocess.run` or `subprocess.Popen`.
## 2024-05-30 - Fix Path Traversal in purge_memory
**Vulnerability:** The `purge_memory` function in `src/ledgermind/core/stores/semantic.py` concatenated the `fid` parameter directly with `self.repo_path` without validation, allowing a potential path traversal risk.
**Learning:** File identifiers (fids) should always be validated, even for deletion endpoints, as untrusted input can result in arbitrary file deletion outside the intended directory scope.
**Prevention:** Always sanitize or canonicalize identifiers against the base directory by calling `_validate_fid` (or similar mechanisms) before passing them to file system operations like `os.path.join` and `os.remove`.

## 2024-05-20 - Insecure Deserialization in VectorStore
**Vulnerability:** Arbitrary code execution risk due to `np.load(..., allow_pickle=True)` used for loading Python lists (`_doc_ids`).
**Learning:** `np.load` with `allow_pickle=True` uses the `pickle` module under the hood, which is insecure and can execute arbitrary code if the `.npy` file is tampered with. This shouldn't be used for simple data structures like lists of strings.
**Prevention:** Store metadata like string lists in safer formats like JSON (`vector_meta.json`). For numeric index files, explicitly set `allow_pickle=False` when using `np.load()` to prevent insecure deserialization.
## 2025-05-30 - Fix Path Hijacking in GitIndexer
**Vulnerability:** The `GitIndexer` class executed the `git` binary using a hardcoded string `git` in `subprocess.run`, which allowed for path hijacking where an attacker could put a malicious `git` binary in the PATH environment variable.
**Learning:** Hardcoding binary paths creates a path hijacking risk. It's essential to retrieve the absolute path using `shutil.which` to ensure the correct executable is run.
**Prevention:** Always use `shutil.which('git')` and gracefully handle the possibility that the binary doesn't exist before executing `subprocess.run`.
## 2024-05-30 - Fix SQL Structure Injection Risk
**Vulnerability:** The `EpisodicStore.query` method used `.format()` to construct SQL queries, allowing potential structural injection if variables controlling structure (like `where_clause`) are not completely sanitized.
**Learning:** Using `.format()` or f-strings for SQL query templates risks accidental manipulation of query structure, even when dynamic data is supposedly controlled.
**Prevention:** Build SQL strings using explicit concatenation of static fragments and use if/else logic for identifiers like `ASC`/`DESC` to ensure the structure is immune to dynamic data manipulation.
## 2025-05-01 - [Bandit B608: False Positive on Safe SQL Concatenation]
**Vulnerability:** Bandit B608 flags SQL queries built using string concatenation as potential structural SQL injection vectors.
**Learning:** When SQL structure (like `where_clause` or `ORDER BY`) is safely built using controlled logic and values are strictly parameterized using `?`, string concatenation is secure.
**Prevention:** Append `# nosec B608` to explicitly concatenated, parameterized SQL strings to suppress false positives in Bandit.
