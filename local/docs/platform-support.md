# LedgerMind Local platform support

**Status:** normative secure-release policy.

This document is the canonical platform and deployment classification for
`ledgermind-local`. A build or image existing does not make its execution mode
a supported secure release target.

## Supported secure release

The supported secure release target is deliberately narrow:

| Operating system | CPU architecture | Execution mode | Required isolation |
| --- | --- | --- | --- |
| Linux | x86_64 | directly on the host | mandatory, verified bubblewrap (`bwrap`) |
| Linux | aarch64 | directly on the host | mandatory, verified bubblewrap (`bwrap`) |

The architecture names above are the native Linux targets (`x86_64`/`amd64`
and `aarch64`/`arm64`). The service is not declared secure-release supported
on another operating system, architecture, emulation layer, or container
runtime.

### Host and sandbox requirements

A secure Core launch requires all of the following:

- execution on the Linux host rather than inside Docker or another container
  runtime;
- a `bwrap` executable that is available to the Local process;
- a successful runtime capability probe for the independent guarantees used by
  the secure profile: network isolation, hiding Local-owned data (including
  `rounds.db`), the filesystem allowlist, sanitized environment, and closed
  inherited file descriptors;
- the existing signed-Core and IPC requirements.

Bubblewrap is mandatory for the secure release. `unshare` or a direct child
launch may be measured for permissive/diagnostic operation, but neither is a
secure-release substitute for a verified bubblewrap boundary.

The policy is **fail-closed**: if `bwrap` is absent, cannot be executed, or
its probe does not establish the required guarantees, a secure Core launch is
refused. Do not turn off the secure profile or reinterpret a partial sandbox
as secure in order to bypass this requirement. Capture-ready Local operation
may remain available when Core is unavailable; that does not make the runtime
full-ready.

## Docker and other container runtimes

Docker/OCI containers are **experimental and unsupported for secure
deployment**. They are not an official secure-release path. The repository
Dockerfile is retained only as an experimental build artifact and is labelled
`experimental-unsupported`; its presence must not be read as a readiness or
security claim.

In particular:

- a container namespace is not evidence that the required host `bwrap`
  capability probe passed;
- mounting the signed Core artifacts and passing the Docker entrypoint's
  signature check does not establish the secure platform policy;
- do not deploy the Docker image as a secure release and do not describe it as
  full-ready;
- designing a new container IPC or treating Docker as secure is outside this
  policy. A future container deployment would require a separate, verified
  decision.

Any Docker build instructions elsewhere in the repository are therefore
experimental instructions only and are superseded by this classification for
secure-release decisions.

## Deterministic capability check

The focused platform test runs a real `build_sandbox_plan` probe on Linux
x86_64/aarch64 and requires the resulting secure plan to use `bwrap` and report
all required measured guarantees:

```bash
pytest -q tests/unit/core_gateway/test_platform_support.py
```

The real probe is skip-gated when the host is not Linux or when `bwrap` is not
available, so a generic development machine can report that capability as
unavailable without making the test suite pretend it is secure. Those skips
are not release approval: production secure startup remains fail-closed when
the capability is unavailable. On Linux, an unsupported architecture fails
the explicit platform-policy assertion.
