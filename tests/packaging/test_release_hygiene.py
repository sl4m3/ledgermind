from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "release-integrations.py"


class IntegrationsReleaseScriptTests(unittest.TestCase):
    def _head(self) -> tuple[str, int]:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
        timestamp = int(
            subprocess.run(
                ["git", "show", "-s", "--format=%ct", "HEAD"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return commit, timestamp

    def _manifest(self, directory: Path, commit: str, commit_timestamp: int) -> Path:
        with (ROOT / "python" / "pyproject.toml").open("rb") as handle:
            integrations_version = tomllib.load(handle)["project"]["version"]
        with (ROOT / "protocol" / "python" / "pyproject.toml").open("rb") as handle:
            protocol_version = tomllib.load(handle)["project"]["version"]
        artifact_names = (
            f"ledgermind_integrations-{integrations_version}-py3-none-any.whl",
            f"ledgermind_integrations-{integrations_version}.tar.gz",
            f"ledgermind_protocol-{protocol_version}-py3-none-any.whl",
            f"ledgermind_protocol-{protocol_version}.tar.gz",
        )
        artifacts = []
        for index, name in enumerate(artifact_names):
            artifact = directory / name
            artifact.write_bytes(f"release-test-{index}".encode())
            artifacts.append(
                {
                    "name": artifact.name,
                    "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    "size_bytes": artifact.stat().st_size,
                }
            )
        manifest = directory / "ledgermind-integrations-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "format": "ledgermind-release-manifest",
                    "schema_version": 1,
                    "component": "ledgermind-integrations",
                    "source_commit": commit,
                    "commit_sha": commit,
                    "source_commit_timestamp": commit_timestamp,
                    "source_archive_sha256": "0" * 64,
                    "version": integrations_version,
                    "versions": {
                        "ledgermind-integrations": integrations_version,
                        "ledgermind-protocol": protocol_version,
                    },
                    "build_time_epoch": commit_timestamp + 1,
                    "checks": {
                        "clean_tracked_source": True,
                        "protocol_wheel_contents": True,
                        "integrations_wheel_contents": True,
                        "license_files": True,
                        "schema_and_conformance_assets": True,
                        "install_smoke": True,
                        "cli_help": True,
                        "hermes_active_round_runtime": True,
                    },
                    "install_smoke": {"passed": True},
                    "artifacts": artifacts,
                    "sha256": {item["name"]: item["sha256"] for item in artifacts},
                }
            ),
            encoding="utf-8",
        )
        return manifest

    def test_help_is_available_without_building(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("system-site-packages", result.stdout)

    def test_dev_extras_declare_quality_and_release_tools(self) -> None:
        for relative in ("python/pyproject.toml", "protocol/python/pyproject.toml"):
            with (ROOT / relative).open("rb") as handle:
                metadata = tomllib.load(handle)
            dev = metadata["project"]["optional-dependencies"]["dev"]
            self.assertTrue(any(str(spec).startswith("pytest>=") for spec in dev), relative)
            self.assertTrue(any(str(spec).startswith("ruff>=") for spec in dev), relative)
            self.assertTrue(any(str(spec).startswith("mypy>=") for spec in dev), relative)
            self.assertTrue(any(str(spec).startswith("build>=") for spec in dev), relative)

    def test_runtime_dependencies_preserve_public_protocol_boundary(self) -> None:
        with (ROOT / "python" / "pyproject.toml").open("rb") as handle:
            integrations = tomllib.load(handle)["project"]["dependencies"]
        with (ROOT / "protocol" / "python" / "pyproject.toml").open("rb") as handle:
            protocol = tomllib.load(handle)["project"]["dependencies"]
        self.assertEqual(integrations, ["ledgermind-protocol>=2.0.0b1,<2.1"])
        self.assertEqual(protocol, ["pydantic>=2.7,<3"])

    def test_protocol_source_inventory_uses_stable_names(self) -> None:
        protocol_source = ROOT / "protocol" / "python" / "src" / "ledgermind_protocol"
        self.assertTrue((protocol_source / "object_facet.py").is_file())
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("ledgermind_protocol/object_facet.py", script)

    def test_lifecycle_runtime_is_required_and_smoke_imported(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        for relative in (
            "ledgermind_integrations/adapters/lifecycle/__init__.py",
            "ledgermind_integrations/adapters/lifecycle/bridge.py",
            "ledgermind_integrations/adapters/lifecycle/config.py",
        ):
            self.assertIn(relative, script)
        self.assertIn(
            "importlib.import_module('ledgermind_integrations.adapters.lifecycle')",
            script,
        )

    def test_verify_rejects_changed_artifact(self) -> None:
        commit, timestamp = self._head()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            manifest = self._manifest(directory, commit, timestamp)
            wheel = next(directory.glob("ledgermind_integrations-*.whl"))
            wheel.write_bytes(b"tampered")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "verify", "--manifest", str(manifest)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "release requires a clean Git checkout"
            if "release requires a clean Git checkout" in result.stderr
            else "SHA-256 mismatch",
            result.stderr,
        )

    def test_verify_rejects_missing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "verify", "--manifest", str(Path(temporary) / "missing.json")],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "release requires a clean Git checkout"
            if "release requires a clean Git checkout" in result.stderr
            else "manifest is required",
            result.stderr,
        )

    def test_verify_rejects_manifest_from_another_commit(self) -> None:
        commit, timestamp = self._head()
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self._manifest(Path(temporary), "0" * len(commit), timestamp)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "verify", "--manifest", str(manifest)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn(
            "release requires a clean Git checkout"
            if "release requires a clean Git checkout" in result.stderr
            else "source commit does not match",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
