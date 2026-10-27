from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ledgermind_local.cli import main
from ledgermind_local.config import CoreSecurityConfig, LocalConfig
from ledgermind_local.core_gateway.doctor import build_core_doctor_report
from ledgermind_local.core_gateway.compatibility import (
    SUPPORTED_KNOWLEDGE_SCHEMA_MAX,
    SUPPORTED_PROTOCOL_MAX,
)
from ledgermind_local.core_gateway.isolation import IsolationRequirements
from ledgermind_local.core_gateway.security_policy import (
    build_core_isolation_requirements,
)
from ledgermind_local.core_gateway.signing import calculate_sha256
from ledgermind_local.paths import ServicePaths


def _write_signed_fake_core(
    paths: ServicePaths,
    *,
    environment_keys: tuple[str, ...] = (
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "RUST_BACKTRACE",
        "LEDGERMIND_CORE_DATA_DIR",
        "PWD",
    ),
) -> None:
    binary = paths.core_data_dir / "bin" / "fake-core"
    signature = paths.core_data_dir / "bin" / "fake-core.sig"
    public_key = paths.core_data_dir / "bin" / "fake-core.pub"
    binary.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    script = f"""#!{sys.executable}
import json
import sys


def read_frame():
    header = sys.stdin.buffer.read(4)
    if not header:
        return None
    size = int.from_bytes(header, 'big')
    return json.loads(sys.stdin.buffer.read(size))


def send(request_id, result):
    payload = json.dumps({{
        'protocol_version': {SUPPORTED_PROTOCOL_MAX},
        'request_id': request_id,
        'status': 'ok',
        'result': result,
    }}, separators=(',', ':')).encode()
    sys.stdout.buffer.write(len(payload).to_bytes(4, 'big') + payload)
    sys.stdout.buffer.flush()


while True:
    request = read_frame()
    if request is None:
        break
    operation = request['operation']
    request_id = request['request_id']
    if operation == 'handshake':
        send(request_id, {{
            'protocol_version': {SUPPORTED_PROTOCOL_MAX},
            'knowledge_schema_version': {SUPPORTED_KNOWLEDGE_SCHEMA_MAX},
            'server_name': 'signed-fake-core',
            'version': 'test-core-1',
            'operations': ['handshake', 'health', 'shutdown'],
        }})
    elif operation == 'health':
        send(request_id, {{
            'healthy': True,
            'backend': 'rust',
            'protocol_version': {SUPPORTED_PROTOCOL_MAX},
            'schema_version': {SUPPORTED_KNOWLEDGE_SCHEMA_MAX},
            'environment_keys': {json.dumps(list(environment_keys))},
        }})
    elif operation == 'shutdown':
        send(request_id, {{'stopped': True}})
        break
"""
    binary.write_text(script, encoding="utf-8")
    os.chmod(binary, 0o700)
    private_key = Ed25519PrivateKey.generate()
    signature.write_bytes(private_key.sign(binary.read_bytes()))
    public_key.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    )


def _doctor_config() -> LocalConfig:
    return LocalConfig(
        config_version=1,
        semantic_language="ru",
        core_backend="process",
        core_binary_path="bin/fake-core",
        core_signature_path="bin/fake-core.sig",
        core_public_key_path="bin/fake-core.pub",
        verify_core_signature=True,
        require_core_network_isolation=False,
        core_security=CoreSecurityConfig(profile="permissive"),
    )


def test_shared_requirements_follow_explicit_secure_and_permissive_profiles() -> None:
    permissive = build_core_isolation_requirements(
        CoreSecurityConfig(profile="permissive"),
        verify_core_signature=False,
    )
    assert permissive == IsolationRequirements()

    secure = build_core_isolation_requirements(
        CoreSecurityConfig(profile="secure"),
        verify_core_signature=True,
    )
    assert secure == IsolationRequirements(
        require_network_isolation=True,
        require_rounds_database_hidden=True,
        require_filesystem_allowlist=True,
        require_environment_sanitized=True,
        require_signature=True,
    )

    permissive_with_one_explicit_guarantee = build_core_isolation_requirements(
        CoreSecurityConfig(
            profile="permissive",
            require_network_isolation=True,
        ),
        verify_core_signature=False,
    )
    assert permissive_with_one_explicit_guarantee == IsolationRequirements(
        require_network_isolation=True,
    )


def test_core_doctor_uses_shared_policy_and_redacts_environment_violations(
    tmp_path: Path,
) -> None:
    paths = ServicePaths(tmp_path / "local")
    paths.home.mkdir(mode=0o700, parents=True)
    _write_signed_fake_core(
        paths,
        environment_keys=(
            "LANG",
            "LC_CTYPE",
            "TZ",
            "OPENAI_API_KEY",
            "HTTP_PROXY",
            "TOKEN",
            "UNEXPECTED_NAME",
        ),
    )

    config = _doctor_config().model_copy(
        update={"require_core_network_isolation": True}
    )
    report = build_core_doctor_report(paths=paths, config=config)
    environment = report["environment"]

    assert report["ok"] is False
    assert report["sandbox"]["requirements"]["network_isolated"] is False
    assert environment["secret_like_count"] == 3
    assert environment["unexpected_count"] == 4
    assert environment["secret_like_keys"] == ["<redacted>"]
    assert environment["unexpected_keys"] == ["<redacted>"]
    serialized = json.dumps(report)
    for name in ("OPENAI_API_KEY", "HTTP_PROXY", "TOKEN", "UNEXPECTED_NAME"):
        assert name not in serialized


def test_core_doctor_reports_missing_signature_without_launching(tmp_path: Path) -> None:
    paths = ServicePaths(tmp_path / "local")
    paths.core_data_dir.mkdir(mode=0o700, parents=True)
    binary = paths.core_data_dir / "bin" / "fake-core"
    binary.parent.mkdir(mode=0o700, exist_ok=True)
    binary.write_bytes(b"unsigned core")

    report = build_core_doctor_report(paths=paths, config=_doctor_config())

    assert report["ok"] is False
    assert report["signature"]["status"] == "failed"
    assert report["health"]["detail"] == "Core was not launched"
    assert report["environment"]["values_exposed"] is False
    assert report["sandbox"]["capabilities"]["binary_signature_verified"] is False


def test_core_doctor_cli_verifies_binary_and_reports_runtime_without_secrets(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    home = tmp_path / "local"
    paths = ServicePaths(home)
    paths.home.mkdir(mode=0o700, parents=True)
    _write_signed_fake_core(paths)
    config = _doctor_config()
    paths.config_file.write_text(config.to_json(), encoding="utf-8")
    monkeypatch.setenv("LEDGERMIND_API_KEY", "[REDACTED]")

    code = main(["--home", str(home), "core", "doctor", "--json"])

    assert code == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["ok"] is True
    assert report["binary"]["sha256"] == calculate_sha256(paths.core_data_dir / "bin" / "fake-core")
    assert report["signature"]["status"] == "verified"
    assert report["version"] == "test-core-1"
    assert report["server_name"] == "signed-fake-core"
    assert report["health"]["protocol_version"] == SUPPORTED_PROTOCOL_MAX
    assert report["health"]["schema_version"] == SUPPORTED_KNOWLEDGE_SCHEMA_MAX
    assert report["sandbox"]["level"] in {"full", "partial"}
    assert report["sandbox"]["capabilities"]["binary_signature_verified"] is True
    assert "missing_requirements" in report["sandbox"]
    assert report["environment"]["secret_like_keys"] == []
    assert report["environment"]["unexpected_keys"] == []
    assert report["environment"]["values_exposed"] is False
    assert "[REDACTED]" not in output
    assert "LEDGERMIND_API_KEY" not in output
