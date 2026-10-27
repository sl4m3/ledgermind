"""Architecture boundary checks for the local service package."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src" / "ledgermind_local"


def _python_files() -> list[Path]:
    return sorted(PACKAGE_ROOT.rglob("*.py"))


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def test_local_does_not_import_integrations_repository() -> None:
    violations = [
        f"{path}:{module}"
        for path in _python_files()
        for module in _imports(path)
        if module == "ledgermind_integrations"
        or module.startswith("ledgermind_integrations.")
    ]
    assert not violations, "Local must not import client integrations:\n" + "\n".join(
        violations
    )


def test_local_boundary_scan_is_not_empty() -> None:
    assert _python_files(), "local architecture scan returned no Python source files"


def test_hermes_client_plugin_is_not_packaged_in_local() -> None:
    assert not (PACKAGE_ROOT / "plugins" / "hermes").exists()


def test_rounds_api_does_not_import_core() -> None:
    rounds_api = PACKAGE_ROOT / "api" / "rounds.py"
    modules = _imports(rounds_api)
    violations = [
        module
        for module in modules
        if module == "ledgermind_core" or module.startswith("ledgermind_core.")
    ]
    assert not violations, "RawRound API must consume ledgermind-protocol, not Core"


def test_local_no_longer_contains_transitional_python_core_surfaces() -> None:
    forbidden = (
        PACKAGE_ROOT / "core_gateway" / "python_backend.py",
        PACKAGE_ROOT / "core_gateway" / "python_backend_migrations.py",
        PACKAGE_ROOT / "core_gateway" / "python_backend_migrations",
        PACKAGE_ROOT / "persistence" / "atom_repository.py",
        PACKAGE_ROOT / "persistence" / "knowledge_repository.py",
        PACKAGE_ROOT / "persistence" / "evidence_repository.py",
        PACKAGE_ROOT / "persistence" / "revision_repository.py",
        PACKAGE_ROOT / "processing" / "bridge.py",
        PACKAGE_ROOT / "persistence" / "split_database.py",
    )

    present = [str(path.relative_to(ROOT)) for path in forbidden if path.exists()]
    assert not present, "transitional Core surfaces remain: " + ", ".join(present)


def test_local_package_does_not_depend_on_python_core() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "ledgermind-core" not in pyproject
