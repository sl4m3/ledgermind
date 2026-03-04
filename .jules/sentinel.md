## 2026-03-04 - Fix partial executable path vulnerability in health check

**Vulnerability:** Bandit flagged `subprocess.run` calls in `src/ledgermind/server/health.py` for executing a command (`git`) using a partial path (B607). This poses a risk of Path Hijacking where a malicious executable named `git` placed earlier in the `PATH` could be inadvertently executed with the application's privileges.

**Learning:** Relying on the environment's `PATH` resolution during a `subprocess` execution without an absolute path creates a point of vulnerability, especially in systems where the `PATH` variable might be manipulated or modified.

**Prevention:** Use `shutil.which('executable_name')` to explicitly resolve the absolute path of the executable before calling `subprocess.run`. Also handle cases where the executable is missing by logging or returning an error instead of letting `subprocess.run` crash or execute maliciously. Ensure the resulting path is used directly and apply `# nosec B603` to acknowledge the validated path execution in Bandit.