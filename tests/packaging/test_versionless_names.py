from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "check-versionless-names.py"


def _load_gate():
    specification = importlib.util.spec_from_file_location(
        "integrations_versionless_gate", SCRIPT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("cannot load versionless-name gate")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


class IntegrationsVersionlessNamesTests(unittest.TestCase):
    def test_current_checkout_is_clean(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("versionless-name gate: clean", result.stdout)

    def test_scan_uses_tracked_paths_and_narrow_allowlists(self) -> None:
        gate = _load_gate()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files = {
                "python/pyproject.toml": (
                    "[project]\n"
                    'version = "v1"\n'
                    'name = "product-v2"\n'
                ),
                "python/src/contracts.py": (
                    'payload = { "schema_version": "v1", "protocol_version": "v2", '
                    '"not_schema_version": "v3" }\n'
                    'provider = "https://provider.example/v1"\n'
                    'local = "http://127.0.0.1:8765/v1"\n'
                    "uuid.uuid4();\n"
                ),
                "python/src/ledgermind_integrations/runtime/spool_migration.py": (
                    'legacy = "ledgermind_context_v1"\n'
                    'operation = "retrieve_context_v2"\n'
                ),
                "migrations/0001_historical-v2.sql": "SELECT 1;\n",
                "scripts/release-integrations.py": 'status = "--porcelain=v1"\n',
            }
            for relative, contents in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents, encoding="utf-8")
            (root / "untracked_v9.py").write_text('value = "v9"\n', encoding="utf-8")
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            subprocess.run(["git", "add", "--", *files], cwd=root, check=True)

            violations = gate.scan(root)
            rendered = "\n".join(gate.format_violation(item) for item in violations)

        self.assertIn("python/pyproject.toml:3:", rendered)
        self.assertIn("python/src/contracts.py:1:", rendered)
        self.assertIn("python/src/contracts.py:3:", rendered)
        self.assertIn("spool_migration.py:2:", rendered)
        self.assertNotIn("untracked_v9.py", rendered)
        self.assertNotIn("provider.example/v1", rendered)
        self.assertNotIn("new_v4", rendered)
        self.assertNotIn("porcelain=v1", rendered)
        self.assertNotIn("0001_historical-v2.sql:0:", rendered)
        self.assertNotIn("spool_migration.py:1:", rendered)
        self.assertNotIn("ledgermind_context_v1", rendered)


if __name__ == "__main__":
    unittest.main()
