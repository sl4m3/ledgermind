from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "release-local.py"


class LocalReleaseScriptTests(unittest.TestCase):
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
        artifact_contents = {
            "local-test-artifact.whl": b"release-test",
            "local-test-artifact.tar.gz": b"release-source-test",
        }
        records: list[dict[str, object]] = []
        digests: dict[str, str] = {}
        for name, content in artifact_contents.items():
            artifact = directory / name
            artifact.write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            records.append(
                {"name": name, "sha256": digest, "size_bytes": artifact.stat().st_size}
            )
            digests[name] = digest
        with (ROOT / "pyproject.toml").open("rb") as handle:
            version = tomllib.load(handle)["project"]["version"]
        manifest = directory / "ledgermind-local-manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "format": "ledgermind-release-manifest",
                    "schema_version": 1,
                    "component": "ledgermind-local",
                    "source_commit": commit,
                    "commit_sha": commit,
                    "source_commit_timestamp": commit_timestamp,
                    "version": version,
                    "build_time_epoch": commit_timestamp + 1,
                    "checks": {"license_files": True},
                    "install_smoke": {"passed": True},
                    "artifacts": records,
                    "sha256": digests,
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
        self.assertIn("dependency-wheel", result.stdout)

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
        self.assertIn("manifest is required", result.stderr)

    def test_dev_extra_declares_release_and_quality_tools(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
        dev_requirements = project["optional-dependencies"]["dev"]
        self.assertIn("build>=1.2", dev_requirements)
        self.assertIn("mypy>=1.10", dev_requirements)

    def test_package_metadata_has_one_stable_cli_entrypoint(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
        self.assertNotIn("v" + "4", project["description"])
        self.assertEqual(project["scripts"], {"ledgermind": "ledgermind_local.cli:main"})

    def test_verify_accepts_manifest_with_matching_artifact(self) -> None:
        commit, timestamp = self._head()
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self._manifest(Path(temporary), commit, timestamp)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "verify", "--manifest", str(manifest)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(manifest))

    def test_verify_rejects_tampered_artifact(self) -> None:
        commit, timestamp = self._head()
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self._manifest(Path(temporary), commit, timestamp)
            artifact = manifest.parent / "local-test-artifact.whl"
            artifact.write_bytes(b"tampered")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "verify", "--manifest", str(manifest)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("SHA-256 mismatch", result.stderr)

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
        self.assertIn("source commit does not match", result.stderr)

    def test_verify_rejects_manifest_with_wrong_schema_version(self) -> None:
        commit, timestamp = self._head()
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self._manifest(Path(temporary), commit, timestamp)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["schema_version"] = 2
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "verify", "--manifest", str(manifest)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("schema version", result.stderr)


if __name__ == "__main__":
    unittest.main()
