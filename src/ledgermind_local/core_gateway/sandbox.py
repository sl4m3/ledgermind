from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import sysconfig
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import TracebackType

from typing_extensions import Self

from .isolation import IsolationCapabilities, IsolationPlan, IsolationRequirements
from .security_policy import (
    CORE_ALLOWED_RUNTIME_INJECTED_ENVIRONMENT_KEYS,
    CORE_ALLOWED_STATIC_ENVIRONMENT_KEYS,
)


class SandboxLevel(str, Enum):
    """Compatibility labels for the pre-A2 sandbox API."""

    FULL = "full"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class SandboxUnavailableError(RuntimeError):
    """Required isolation guarantees are not available on this host."""


@dataclass(frozen=True, slots=True)
class _ProbeResult:
    network_isolated: bool
    rounds_database_hidden: bool
    filesystem_allowlisted: bool
    environment_sanitized: bool
    file_descriptors_closed: bool


# The helper intentionally uses only the Python standard library.  It reports
# independent facts instead of collapsing them into a single sandbox level.
_PROBE_SCRIPT = r'''
import json
import os
import pathlib
import socket
import sys

core_dir = pathlib.Path(sys.argv[1])
blocked_markers = tuple(pathlib.Path(item) for item in json.loads(sys.argv[2]))
rounds_path = pathlib.Path(sys.argv[3]) if sys.argv[3] else None
port = int(sys.argv[4])
expected_environment = set(json.loads(sys.argv[5]))
write_marker = core_dir / sys.argv[6]
sentinel_fd = int(sys.argv[7])

try:
    connection = socket.create_connection(("127.0.0.1", port), timeout=0.25)
except OSError:
    network_isolated = True
else:
    connection.close()
    network_isolated = False

blocked_hidden = bool(blocked_markers)
for marker in blocked_markers:
    try:
        marker.read_bytes()
    except OSError:
        continue
    blocked_hidden = False
    break

rounds_database_hidden = False
if rounds_path is not None:
    try:
        rounds_path.read_bytes()
    except OSError:
        rounds_database_hidden = True

try:
    write_marker.write_bytes(b"isolation-probe")
    filesystem_allowlisted = write_marker.read_bytes() == b"isolation-probe"
except OSError:
    filesystem_allowlisted = False
finally:
    write_marker.unlink(missing_ok=True)

environment_sanitized = set(os.environ).issubset(expected_environment)
try:
    sentinel_inherited = os.path.exists(f"/proc/self/fd/{sentinel_fd}")
except OSError:
    sentinel_inherited = False
file_descriptors_closed = not sentinel_inherited

print(json.dumps({
    "network_isolated": network_isolated,
    "rounds_database_hidden": rounds_database_hidden,
    "filesystem_allowlisted": filesystem_allowlisted and blocked_hidden,
    "environment_sanitized": environment_sanitized,
    "file_descriptors_closed": file_descriptors_closed,
}, separators=(",", ":")))
'''


@dataclass(frozen=True, slots=True)
class SandboxPlan(IsolationPlan):
    """Compatibility wrapper exposing the legacy enum-valued level."""

    @property
    def level(self) -> SandboxLevel:
        if self.capabilities.sandbox_backend == "unavailable":
            return SandboxLevel.UNAVAILABLE
        if all(
            (
                self.capabilities.network_isolated,
                self.capabilities.rounds_database_hidden,
                self.capabilities.filesystem_allowlisted,
                self.capabilities.environment_sanitized,
                self.capabilities.file_descriptors_closed,
            )
        ):
            return SandboxLevel.FULL
        return SandboxLevel.PARTIAL


def build_sandbox_plan(
    command: Sequence[str],
    *,
    core_data_dir: Path,
    blocked_data_dirs: Sequence[Path] = (),
    rounds_database_path: Path | None = None,
    runtime_paths: Sequence[str | Path] = (),
    binary_signature_verified: bool = False,
    required: bool = False,
    requirements: IsolationRequirements | None = None,
    strict: bool | None = None,
    semantic_language: str | None = None,
) -> SandboxPlan:
    """Build a Core command and measure independent isolation capabilities.

    ``required`` is retained for compatibility and means that network
    isolation is mandatory.  New callers can provide all five independent
    requirements through ``requirements``.  A required profile fails closed;
    a permissive profile returns the command with explicit false capabilities.
    """

    original = tuple(str(part) for part in command)
    if not original or any(not part for part in original):
        raise ValueError("Core command must not be empty")
    core_dir = Path(core_data_dir).expanduser()
    blocked_dirs = tuple(Path(item).expanduser() for item in blocked_data_dirs)
    explicit_runtime_paths = tuple(Path(item).expanduser() for item in runtime_paths)
    isolation_requirements = requirements or IsolationRequirements(
        require_network_isolation=required
    )
    strict_mode = required if strict is None else strict
    probe_context = _ProbeContext(
        core_data_dir=core_dir,
        blocked_data_dirs=blocked_dirs,
        rounds_database_path=(
            Path(rounds_database_path).expanduser()
            if rounds_database_path is not None
            else None
        ),
    )
    attempts: list[str] = []

    with probe_context:
        bwrap = shutil.which("bwrap")
        if bwrap:
            bwrap_environment = _sandbox_environment(
                core_dir,
                original,
                semantic_language=semantic_language,
            )
            bwrap_prefix = _build_bwrap_prefix(
                bwrap,
                original,
                core_dir,
                blocked_dirs,
                runtime_paths=explicit_runtime_paths,
                extra_runtime_paths=_probe_runtime_paths(),
                environment=bwrap_environment,
            )
            bwrap_probe = _probe_command(
                _build_probe_invocation(
                    bwrap_prefix,
                    probe_context,
                    expected_environment=bwrap_environment,
                ),
                core_dir,
            )
            if bwrap_probe:
                capabilities = _capabilities_from_probe(
                    bwrap_probe,
                    backend="bwrap",
                    detail="bwrap verified the available independent guarantees",
                    binary_signature_verified=binary_signature_verified,
                )
                plan = SandboxPlan(
                    command=bwrap_prefix + ("--",) + original,
                    capabilities=capabilities,
                )
                return _finish_plan(
                    plan,
                    requirements=isolation_requirements,
                    strict=strict_mode,
                )
            attempts.append("bwrap probe failed")

        unshare = shutil.which("unshare")
        if unshare:
            unshare_prefix = (unshare, "--net")
            unshare_probe = _probe_command(
                _build_probe_invocation(unshare_prefix, probe_context),
                core_dir,
            )
            if unshare_probe:
                capabilities = _capabilities_from_probe(
                    unshare_probe,
                    backend="unshare",
                    detail=(
                        "unshare verified network isolation; filesystem, rounds database, "
                        "and child-process guarantees are not provided"
                    ),
                    binary_signature_verified=binary_signature_verified,
                )
                plan = SandboxPlan(
                    command=unshare_prefix + ("--",) + original,
                    capabilities=capabilities,
                )
                return _finish_plan(
                    plan,
                    requirements=isolation_requirements,
                    strict=strict_mode,
                )
            attempts.append("unshare probe failed")

        direct_probe = _probe_command(
            _build_probe_invocation((), probe_context),
            core_dir,
        )
        if direct_probe:
            capabilities = _capabilities_from_probe(
                direct_probe,
                backend="none",
                detail="sandbox backend unavailable; only directly measured properties apply",
                binary_signature_verified=binary_signature_verified,
            )
        else:
            capabilities = IsolationCapabilities(
                sandbox_backend="none",
                detail="sandbox backend unavailable; isolation guarantees not established",
            )

    if attempts:
        detail = f"{capabilities.detail}: {', '.join(attempts)}"
        capabilities = IsolationCapabilities(
            network_isolated=capabilities.network_isolated,
            rounds_database_hidden=capabilities.rounds_database_hidden,
            filesystem_allowlisted=capabilities.filesystem_allowlisted,
            environment_sanitized=capabilities.environment_sanitized,
            file_descriptors_closed=capabilities.file_descriptors_closed,
            child_process_creation_blocked=capabilities.child_process_creation_blocked,
            binary_signature_verified=capabilities.binary_signature_verified,
            sandbox_backend=capabilities.sandbox_backend,
            detail=detail,
        )
    plan = SandboxPlan(command=original, capabilities=capabilities)
    return _finish_plan(plan, requirements=isolation_requirements, strict=strict_mode)


def _finish_plan(
    plan: SandboxPlan,
    *,
    requirements: IsolationRequirements,
    strict: bool,
) -> SandboxPlan:
    missing = requirements.missing(plan.capabilities)
    if strict and missing:
        raise SandboxUnavailableError(
            "required Core isolation guarantees missing: " + ", ".join(missing)
        )
    return plan


def _capabilities_from_probe(
    result: _ProbeResult | bool,
    *,
    backend: str,
    detail: str,
    binary_signature_verified: bool,
) -> IsolationCapabilities:
    if isinstance(result, bool):
        # A boolean is only a legacy probe result; it is not evidence for any
        # independent guarantee.  Keep the seam without manufacturing a
        # filesystem or network capability from an unstructured result.
        return IsolationCapabilities(
            binary_signature_verified=binary_signature_verified,
            sandbox_backend=backend,
            detail=f"{detail}; detailed probe result unavailable",
        )
    return IsolationCapabilities(
        network_isolated=result.network_isolated,
        rounds_database_hidden=result.rounds_database_hidden,
        filesystem_allowlisted=result.filesystem_allowlisted,
        environment_sanitized=result.environment_sanitized,
        file_descriptors_closed=result.file_descriptors_closed,
        binary_signature_verified=binary_signature_verified,
        sandbox_backend=backend,
        detail=detail,
    )


class _ProbeContext:
    def __init__(
        self,
        *,
        core_data_dir: Path,
        blocked_data_dirs: Sequence[Path],
        rounds_database_path: Path | None,
    ) -> None:
        self.core_data_dir = core_data_dir
        self.blocked_data_dirs = tuple(blocked_data_dirs)
        self.rounds_database_path = rounds_database_path
        self.marker_paths: list[Path] = []
        self.marker_name = f".ledgermind-isolation-{uuid.uuid4().hex}"
        self.write_marker_name = f".ledgermind-isolation-write-{uuid.uuid4().hex}"
        self.server: socket.socket | None = None
        self.sentinel_fd: int | None = None

    def __enter__(self) -> Self:
        for directory in self.blocked_data_dirs:
            if not directory.is_dir():
                continue
            marker = directory / self.marker_name
            try:
                marker.write_bytes(b"blocked-data-probe")
            except OSError:
                continue
            self.marker_paths.append(marker)
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        candidate = 1000
        while True:
            try:
                os.fstat(candidate)
            except OSError:
                break
            candidate += 1
        try:
            self.sentinel_fd = os.dup2(
                self.server.fileno(), candidate, inheritable=True
            )
        except TypeError:
            self.sentinel_fd = os.dup2(self.server.fileno(), candidate)
            os.set_inheritable(self.sentinel_fd, True)
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if self.server is not None:
            self.server.close()
        if self.sentinel_fd is not None:
            os.close(self.sentinel_fd)
        for marker in self.marker_paths:
            marker.unlink(missing_ok=True)

    @property
    def port(self) -> int:
        if self.server is None:
            raise RuntimeError("probe context is not active")
        return int(self.server.getsockname()[1])


def _build_probe_invocation(
    prefix: Sequence[str],
    context: _ProbeContext,
    *,
    expected_environment: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    expected = sorted(
        (expected_environment or _sanitized_environment(context.core_data_dir)).keys()
    )
    blocked_markers = [str(path) for path in context.marker_paths]
    rounds_path = ""
    if context.rounds_database_path is not None and context.rounds_database_path.is_file():
        rounds_path = str(context.rounds_database_path)
    probe = (
        str(Path(sys.executable).expanduser().resolve()),
        "-S",
        "-c",
        _PROBE_SCRIPT,
        str(context.core_data_dir),
        json.dumps(blocked_markers),
        rounds_path,
        str(context.port),
        json.dumps(expected),
        context.write_marker_name,
        str(context.sentinel_fd if context.sentinel_fd is not None else -1),
    )
    if prefix:
        return tuple(prefix) + ("--",) + probe
    return probe


def _build_bwrap_prefix(
    bwrap: str,
    command: Sequence[str],
    core_data_dir: Path,
    blocked_data_dirs: Sequence[Path],
    *,
    runtime_paths: Sequence[Path] = (),
    extra_runtime_paths: Sequence[Path] = (),
    environment: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    mount_paths = _runtime_paths_for_command(command)
    declared_paths = _allowed_runtime_paths(runtime_paths, blocked_data_dirs)
    mount_paths.extend(declared_paths)
    for path in declared_paths:
        if path.is_file():
            mount_paths.extend(_ldd_dependencies(path))
        elif path.is_dir():
            for extension in path.rglob("*.so"):
                mount_paths.extend(_ldd_dependencies(extension))
    mount_paths.extend(extra_runtime_paths)
    python_home = _python_runtime_home(command)
    if python_home is not None:
        mount_paths.extend(_python_runtime_paths(python_home))
    mount_paths.extend(_command_file_paths(command, blocked_data_dirs, core_data_dir))
    seen: set[str] = set()
    mount_args: list[str] = []
    for path in mount_paths:
        normalized = str(path)
        if (
            normalized in seen
            or not path.exists()
            or (python_home is not None and path.name == "pyvenv.cfg")
        ):
            continue
        seen.add(normalized)
        mount_args.extend(("--ro-bind", str(_mount_source(path)), normalized))

    destinations = [
        *mount_paths,
        core_data_dir,
        Path("/dev"),
        Path("/proc"),
        Path("/tmp"),
        *blocked_data_dirs,
        Path(command[0]).expanduser(),
    ]

    prefix: list[str] = [
        bwrap,
        "--unshare-user",
        "--unshare-net",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--tmpfs",
        "/tmp",
        *_directory_args(destinations),
        *mount_args,
        "--bind",
        str(core_data_dir),
        str(core_data_dir),
        "--dev",
        "/dev",
        "--proc",
        "/proc",
    ]
    for blocked_data_dir in blocked_data_dirs:
        prefix.extend(("--tmpfs", str(blocked_data_dir)))

    # The Core binary is read-only even when it lives below the writable Core
    # data directory.  The later mount deliberately overlays only that file.
    executable = Path(command[0]).expanduser()
    prefix.extend(("--ro-bind", str(_mount_source(executable)), str(executable)))
    prefix.extend(("--chdir", str(core_data_dir)))
    sandbox_environment = environment or _sandbox_environment(core_data_dir, command)
    for name, value in sandbox_environment.items():
        prefix.extend(("--setenv", name, value))
    return tuple(prefix)


def _mount_source(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError:
        return path


def _directory_args(destinations: Sequence[Path]) -> tuple[str, ...]:
    directories: set[str] = set()
    for destination in destinations:
        path = destination if destination.is_dir() else destination.parent
        for parent in path.parents:
            if str(parent) == "/":
                break
            directories.add(str(parent))
        if str(path) != "/":
            directories.add(str(path))
    ordered = sorted(directories, key=lambda item: (item.count("/"), item))
    return tuple(argument for directory in ordered for argument in ("--dir", directory))


def _runtime_paths_for_command(command: Sequence[str]) -> list[Path]:
    if not command:
        return []
    executable = Path(command[0]).expanduser()
    if not executable.is_absolute():
        resolved = shutil.which(str(executable))
        executable = Path(resolved) if resolved else executable
    paths = [executable]
    virtualenv_config = executable.parent.parent / "pyvenv.cfg"
    if virtualenv_config.is_file():
        paths.append(virtualenv_config)
    paths.extend(_ldd_dependencies(executable))
    interpreter = _shebang_interpreter(executable)
    if interpreter is not None and interpreter != executable:
        paths.extend(_runtime_paths_for_command((str(interpreter),)))
    return paths


def _allowed_runtime_paths(
    runtime_paths: Sequence[Path], blocked_data_dirs: Sequence[Path]
) -> list[Path]:
    """Keep caller-declared runtime mounts inside the explicit allowlist."""

    allowed: list[Path] = []
    for path in runtime_paths:
        candidate = Path(path).expanduser()
        if (
            not candidate.is_absolute()
            or not candidate.exists()
            or any(_is_path_within(candidate, blocked) for blocked in blocked_data_dirs)
        ):
            continue
        allowed.append(candidate)
    return allowed


def _command_file_paths(
    command: Sequence[str], blocked_data_dirs: Sequence[Path], core_data_dir: Path
) -> list[Path]:
    """Mount absolute file arguments needed by script-based Core test shims."""

    paths: list[Path] = []
    for argument in command[1:]:
        path = Path(argument).expanduser()
        if (
            path.is_absolute()
            and path.is_file()
            and not _is_path_within(path, core_data_dir)
            and not any(_is_path_within(path, blocked) for blocked in blocked_data_dirs)
        ):
            paths.append(path)
    return paths


def _is_path_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _python_runtime_home(command: Sequence[str]) -> Path | None:
    """Find the base prefix needed by a virtual-environment Python shim."""

    if not command:
        return None
    executable = Path(command[0]).expanduser()
    if not executable.is_absolute():
        resolved = shutil.which(str(executable))
        executable = Path(resolved) if resolved else executable
    if executable.name.startswith("python"):
        config = executable.parent.parent / "pyvenv.cfg"
        if config.is_file():
            try:
                lines = config.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            for line in lines:
                name, separator, raw_home = line.partition("=")
                if separator and name.strip() == "home":
                    home = Path(raw_home.strip()).expanduser()
                    if not home.is_absolute():
                        home = config.parent / home
                    return home.resolve().parent
    interpreter = _shebang_interpreter(executable)
    if interpreter is not None and interpreter != executable:
        return _python_runtime_home((str(interpreter),))
    return None


def _python_runtime_paths(python_home: Path) -> tuple[Path, ...]:
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    paths = [
        path
        for path in (
            python_home / "lib" / version,
            python_home / "lib64" / version,
        )
        if path.is_dir()
    ]
    for path in paths:
        for extension in path.rglob("*.so"):
            paths.extend(_ldd_dependencies(extension))
    return tuple(paths)


def _probe_runtime_paths() -> tuple[Path, ...]:
    paths = _runtime_paths_for_command((sys.executable,))
    paths.append(Path(sys.executable).expanduser().resolve())
    for key in ("stdlib", "platstdlib"):
        value = sysconfig.get_paths().get(key)
        if value:
            paths.append(Path(value))
    return tuple(paths)


def _shebang_interpreter(executable: Path) -> Path | None:
    if not executable.is_file():
        return None
    try:
        first_line = executable.read_bytes().splitlines()[0].decode("utf-8")
    except (IndexError, OSError, UnicodeDecodeError):
        return None
    if not first_line.startswith("#!"):
        return None
    interpreter = first_line[2:].strip().split(maxsplit=1)[0]
    if interpreter == "/usr/bin/env":
        return None
    path = Path(interpreter).expanduser()
    if not path.is_absolute():
        resolved = shutil.which(interpreter)
        return Path(resolved) if resolved else None
    return path


def _ldd_dependencies(executable: Path) -> list[Path]:
    if not executable.is_file():
        return []
    try:
        completed = subprocess.run(
            ("ldd", str(executable)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    dependencies: list[Path] = []
    for line in completed.stdout.splitlines():
        candidate: str | None = None
        if "=>" in line:
            left, right = line.split("=>", 1)
            left = left.strip()
            candidate = left if left.startswith("/") else right.strip().split(" ", 1)[0]
        elif line.lstrip().startswith("/"):
            candidate = line.strip().split(" ", 1)[0]
        if candidate and candidate.startswith("/"):
            path = Path(candidate)
            if path.is_file():
                dependencies.append(path)
    return dependencies


def _sanitized_environment(core_data_dir: Path) -> dict[str, str]:
    fixed_values = {
        "RUST_BACKTRACE": "0",
        "LEDGERMIND_CORE_DATA_DIR": str(core_data_dir),
        "PWD": str(core_data_dir),
    }
    environment: dict[str, str] = {}
    for name in sorted(
        CORE_ALLOWED_STATIC_ENVIRONMENT_KEYS
        | CORE_ALLOWED_RUNTIME_INJECTED_ENVIRONMENT_KEYS
    ):
        value = fixed_values.get(name, os.environ.get(name))
        if value:
            environment[name] = value
    return environment


def _sandbox_environment(
    core_data_dir: Path,
    command: Sequence[str],
    *,
    semantic_language: str | None = None,
) -> dict[str, str]:
    environment = _sanitized_environment(core_data_dir)
    if semantic_language:
        environment["LEDGERMIND_SEMANTIC_LANGUAGE"] = semantic_language
    python_home = _python_runtime_home(command)
    if python_home is not None:
        # Only a Python test/runtime shim needs this.  The production Rust
        # Core has no Python runtime invariant and never receives PYTHONHOME.
        # A bwrap namespace does not preserve a shim virtualenv's pyvenv.cfg
        # lookup chain, so point that shim at the read-only base runtime.
        environment["PYTHONHOME"] = str(python_home)
    return environment


def _probe_command(
    command: Sequence[str],
    core_data_dir: Path,
) -> _ProbeResult | bool | None:
    try:
        completed = subprocess.run(
            tuple(command),
            cwd=str(core_data_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            close_fds=True,
            env=_sanitized_environment(core_data_dir),
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError):
        return True
    try:
        return _ProbeResult(
            network_isolated=bool(payload["network_isolated"]),
            rounds_database_hidden=bool(payload["rounds_database_hidden"]),
            filesystem_allowlisted=bool(payload["filesystem_allowlisted"]),
            environment_sanitized=bool(payload["environment_sanitized"]),
            file_descriptors_closed=bool(payload["file_descriptors_closed"]),
        )
    except (KeyError, TypeError):
        return None


__all__ = [
    "SandboxLevel",
    "SandboxPlan",
    "SandboxUnavailableError",
    "build_sandbox_plan",
]
