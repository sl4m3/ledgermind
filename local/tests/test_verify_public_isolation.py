"""Tests for automated public repository isolation and core code separation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Import isolation verification audit functions
REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
VERIFY_SCRIPT = TOOLS_DIR / "verify-public-isolation.py"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import importlib.util

spec = importlib.util.spec_from_file_location("verify_public_isolation", VERIFY_SCRIPT)
assert spec and spec.loader
verify_mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = verify_mod
spec.loader.exec_module(verify_mod)


def test_verify_public_isolation_cli_passes():
    """Verify that the verification script CLI runs and passes with exit code 0."""
    result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--repo-root", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Script failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    assert "ALL TIERS PASSED" in result.stdout


def test_verify_public_isolation_cli_json():
    """Verify that the verification script JSON output is complete and clean."""
    result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--repo-root", str(REPO_ROOT), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Script failed:\n{result.stderr}"
    data = json.loads(result.stdout)
    assert data["status"] == "passed"
    assert data["violations_count"] == 0

    tiers = data["tiers"]
    assert "tier_1_file_tree" in tiers
    assert "tier_2_source_ast" in tiers
    assert "tier_3_distribution_package" in tiers
    assert "tier_4_bundle_payload" in tiers

    for tier_key, tier_data in tiers.items():
        assert tier_data["status"] == "passed", f"{tier_key} failed: {tier_data['violations']}"
        assert tier_data["violations"] == []


def test_tier1_detects_forbidden_file_tree(tmp_path: Path):
    """Verify Tier 1 detects forbidden Rust source files, Cargo manifests, and directories."""
    # Clean repo should pass
    violations = verify_mod.audit_repo_file_tree(tmp_path)
    assert violations == []

    # Rust file
    rs_file = tmp_path / "leak.rs"
    rs_file.write_text("fn main() {}", encoding="utf-8")
    violations = verify_mod.audit_repo_file_tree(tmp_path)
    assert any("Forbidden Rust source file found" in v for v in violations)
    rs_file.unlink()

    # Cargo manifest
    cargo_file = tmp_path / "Cargo.toml"
    cargo_file.write_text("[package]\nname = 'leak'", encoding="utf-8")
    violations = verify_mod.audit_repo_file_tree(tmp_path)
    assert any("Forbidden Cargo manifest found" in v for v in violations)
    cargo_file.unlink()

    # Forbidden root directory
    core_dir = tmp_path / "core"
    core_dir.mkdir()
    violations = verify_mod.audit_repo_file_tree(tmp_path)
    assert any("Forbidden private directory at repository root: core/" in v for v in violations)


def test_tier2_detects_forbidden_ast_imports(tmp_path: Path):
    """Verify Tier 2 detects forbidden imports of internal core and lab modules."""
    test_py = tmp_path / "test_module.py"

    # Clean file
    test_py.write_text("import os\nimport sys\n", encoding="utf-8")
    violations = verify_mod.audit_source_code(tmp_path)
    assert violations == []

    # Import ledgermind_lab
    test_py.write_text("import " + "ledgermind_lab" + ".benchmark\n", encoding="utf-8")
    violations = verify_mod.audit_source_code(tmp_path)
    assert any("Forbidden import 'ledgermind_lab.benchmark'" in v for v in violations)

    # From-import core.crates
    test_py.write_text("from " + "core.crates" + " import daemon\n", encoding="utf-8")
    violations = verify_mod.audit_source_code(tmp_path)
    assert any("Forbidden from-import 'core.crates'" in v for v in violations)

    # Import ledgermind_cloud.service
    test_py.write_text("from " + "ledgermind_cloud" + " import service\n", encoding="utf-8")
    violations = verify_mod.audit_source_code(tmp_path)
    assert any("Forbidden from-import 'ledgermind_cloud.service'" in v for v in violations)


def test_tier4_detects_invalid_bundle(tmp_path: Path):
    """Verify Tier 4 detects non-ELF binaries and missing signatures in bundle payload."""
    bundle_dir = tmp_path / "bundle"
    bin_dir = bundle_dir / "bin"
    sig_dir = bundle_dir / "signatures"
    bin_dir.mkdir(parents=True)
    sig_dir.mkdir(parents=True)

    # Missing core binary
    violations = verify_mod.audit_bundle_payload(bundle_dir)
    assert any("Bundle is missing core binary" in v for v in violations)

    # Non-ELF core binary
    core_binary = bin_dir / "ledgermind-core"
    core_binary.write_bytes(b"NOT_AN_ELF_BINARY")
    violations = verify_mod.audit_bundle_payload(bundle_dir)
    assert any("is not an ELF binary" in v for v in violations)

    # Valid ELF binary but missing signature
    elf_magic = b"\x7fELF" + (b"\x00" * 60)
    core_binary.write_bytes(elf_magic)
    violations = verify_mod.audit_bundle_payload(bundle_dir)
    assert any("Bundle is missing detached core signature" in v for v in violations)

    # Empty signature
    sig_file = sig_dir / "ledgermind-core.sig"
    sig_file.write_bytes(b"")
    violations = verify_mod.audit_bundle_payload(bundle_dir)
    assert any("is empty" in v for v in violations)

    # Valid signature file, but embedded .rs file in bundle
    sig_file.write_bytes(b"valid_signature_placeholder_bytes" * 2)
    leaked_rs = bundle_dir / "internal.rs"
    leaked_rs.write_text("fn leak() {}", encoding="utf-8")
    violations = verify_mod.audit_bundle_payload(bundle_dir)
    assert any("Bundle contains forbidden Rust source file" in v for v in violations)
