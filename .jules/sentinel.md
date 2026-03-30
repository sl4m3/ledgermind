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
