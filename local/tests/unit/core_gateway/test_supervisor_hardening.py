from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

from ledgermind_local.core_gateway.isolation import IsolationRequirements
from ledgermind_local.core_gateway.security_policy import (
    CORE_ALLOWED_RUNTIME_INJECTED_ENVIRONMENT_KEYS,
)
from ledgermind_local.core_gateway.supervisor import (
    CoreSupervisor,
    CoreSupervisorBusy,
    CoreSupervisorError,
)


def test_diagnostic_request_fails_fast_when_core_channel_is_busy(
    tmp_path: Path,
) -> None:
    supervisor = CoreSupervisor(
        [sys.executable, "-c", "pass"],
        core_data_dir=tmp_path,
        semantic_language="ru",
    )
    acquired = threading.Event()
    release = threading.Event()

    def hold_channel() -> None:
        with supervisor._lock:
            acquired.set()
            release.wait(timeout=2)

    holder = threading.Thread(target=hold_channel)
    holder.start()
    assert acquired.wait(timeout=1)
    started = time.monotonic()
    try:
        with pytest.raises(CoreSupervisorBusy):
            supervisor.try_request(
                "get_object_facet_statistics",
                lock_timeout_seconds=0.02,
            )
    finally:
        release.set()
        holder.join(timeout=1)

    assert time.monotonic() - started < 0.25


def test_core_child_receives_restricted_environment_cwd_and_fds(
    tmp_path: Path, monkeypatch
) -> None:
    core_data_dir = tmp_path / "core"
    core_data_dir.mkdir(mode=0o700)
    local_data_dir = tmp_path / "local"
    local_data_dir.mkdir(mode=0o700)
    rounds_database = local_data_dir / "rounds.db"
    rounds_database.write_bytes(b"local-owned fixture")
    report_path = core_data_dir / "report.json"
    probe_path = core_data_dir / "probe.py"
    probe_path.write_text(
        "import json, os, pathlib, sys, time\n"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({\n"
        "  'cwd': os.getcwd(),\n"
        "  'env': dict(os.environ),\n"
        "  'inherited_fd': os.path.exists('/proc/self/fd/' + sys.argv[2]),\n"
        "  'rounds_visible': pathlib.Path(sys.argv[3]).exists(),\n"
        "}), encoding='utf-8')\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    monkeypatch.setenv("LC_CTYPE", "C.UTF-8")
    monkeypatch.setenv("LEDGERMIND_SEMANTIC_LANGUAGE", "ru")
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setenv("LEDGERMIND_TEST_SECRET", "[REDACTED]")
    monkeypatch.setenv("LEDGERMIND_ROUNDS_DB", str(tmp_path / "rounds.db"))
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid")
    inherited_fd = os.open(os.devnull, os.O_RDONLY)
    os.set_inheritable(inherited_fd, True)

    supervisor = CoreSupervisor(
        [
            sys.executable,
            str(probe_path),
            str(report_path),
            str(inherited_fd),
            str(rounds_database),
        ],
        core_data_dir=core_data_dir,
        blocked_data_dirs=(local_data_dir,),
        rounds_database_path=rounds_database,
        semantic_language="ru",
    )
    try:
        supervisor._spawn_locked()
        deadline = time.monotonic() + 2.0
        while not report_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        supervisor._terminate_locked()
        os.close(inherited_fd)

    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["cwd"] == str(core_data_dir)
    assert report["inherited_fd"] is False
    if supervisor.isolation_capabilities.rounds_database_hidden:
        assert report["rounds_visible"] is False
    else:
        assert report["rounds_visible"] is True
    assert report["env"].pop("PWD") == str(core_data_dir)
    expected_environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "RUST_BACKTRACE": "0",
        "LEDGERMIND_CORE_DATA_DIR": str(core_data_dir),
        "LEDGERMIND_SEMANTIC_LANGUAGE": "ru",
    }
    if supervisor.isolation_capabilities.sandbox_backend == "bwrap":
        expected_environment.update(
            {
                name: os.environ[name]
                for name in CORE_ALLOWED_RUNTIME_INJECTED_ENVIRONMENT_KEYS
                if os.environ.get(name)
            }
        )
    # PYTHONHOME is an implementation detail for the Python test/runtime shim;
    # it is not part of the production Core environment contract.
    report["env"].pop("PYTHONHOME", None)
    assert report["env"] == expected_environment


def test_full_network_sandbox_cannot_reach_host_loopback(tmp_path: Path) -> None:
    core_data_dir = tmp_path / "core"
    core_data_dir.mkdir(mode=0o700)
    report_path = core_data_dir / "network.json"
    probe_path = core_data_dir / "network_probe.py"
    probe_path.write_text(
        "import json, pathlib, socket, sys\n"
        "try:\n"
        "    socket.create_connection(('127.0.0.1', int(sys.argv[2])), timeout=0.5)\n"
        "except OSError:\n"
        "    connected = False\n"
        "else:\n"
        "    connected = True\n"
        "pathlib.Path(sys.argv[1]).write_text(json.dumps({'connected': connected}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    supervisor = CoreSupervisor(
        [sys.executable, str(probe_path), str(report_path), str(server.getsockname()[1])],
        core_data_dir=core_data_dir,
        semantic_language="ru",
    )
    try:
        supervisor._spawn_locked()
        if not supervisor.isolation_capabilities.network_isolated:
            pytest.skip("network namespace is unavailable on this host")
        deadline = time.monotonic() + 2.0
        while not report_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
    finally:
        supervisor._terminate_locked()
        server.close()

    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["connected"] is False


def test_strict_profile_refuses_when_rounds_database_cannot_be_hidden(
    tmp_path: Path, monkeypatch
) -> None:
    core_data_dir = tmp_path / "core"
    core_data_dir.mkdir(mode=0o700)
    local_data_dir = tmp_path / "local"
    local_data_dir.mkdir(mode=0o700)
    rounds_database = local_data_dir / "rounds.db"
    rounds_database.write_bytes(b"local-owned fixture")
    monkeypatch.setattr(
        "ledgermind_local.core_gateway.sandbox.shutil.which",
        lambda _: None,
    )

    supervisor = CoreSupervisor(
        [sys.executable, "-c", "pass"],
        core_data_dir=core_data_dir,
        blocked_data_dirs=(local_data_dir,),
        rounds_database_path=rounds_database,
        isolation_requirements=IsolationRequirements(
            require_network_isolation=True,
            require_rounds_database_hidden=True,
            require_filesystem_allowlist=True,
            require_environment_sanitized=True,
        ),
        strict_isolation=True,
        semantic_language="ru",
    )

    with pytest.raises(CoreSupervisorError, match="rounds_database_hidden"):
        supervisor.start()

    assert "rounds_database_hidden" in supervisor.isolation_missing_requirements
