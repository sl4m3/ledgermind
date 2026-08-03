"""Architecture boundary checks for the core package."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
PACKAGE_ROOT = SRC_ROOT / "ledgermind_core"

FORBIDDEN_DOMAIN_IMPORTS = {"application", "ports", "contracts"}
FORBIDDEN_CORE_IMPORTS = {
    "fastapi",
    "sqlite3",
    "sqlalchemy",
    "git",
    "numpy",
    "llama_cpp",
}


def _python_files() -> list[Path]:
    return [path for path in PACKAGE_ROOT.rglob("*.py")]


def _import_violations(
    tree: ast.AST, path: Path, forbidden: set[str], scope: str
) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name.split(".")[0]
                if module_name in forbidden:
                    violations.append(
                        f"{path}:{node.lineno}: {scope} -> import {alias.name}"
                    )
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            module_name = node.module.split(".")[0]
            if module_name in forbidden:
                violations.append(
                    f"{path}:{node.lineno}: {scope} -> from {node.module} import ..."
                )
    return violations


def _runtime_call_violations(tree: ast.AST, path: Path) -> list[str]:
    os_aliases: set[str] = set()
    path_module_aliases: set[str] = set()
    path_aliases: set[str] = set()
    os_imported_environs: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top == "os":
                    os_aliases.add(alias.asname or "os")
                if top == "pathlib":
                    path_module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "os":
                for alias in node.names:
                    imported_name = alias.name
                    local_name = alias.asname or alias.name
                    if imported_name == "environ":
                        os_aliases.add(local_name)
                    os_imported_environs.add(local_name)
            if node.module == "pathlib":
                for alias in node.names:
                    if alias.name == "Path":
                        path_aliases.add(alias.asname or "Path")
                    if alias.name == "pathlib":
                        path_module_aliases.add(alias.asname or "pathlib")

    violations: list[str] = []

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in os_aliases
            and node.attr == "environ"
            and isinstance(node.ctx, ast.Load)
        ):
            violations.append(f"{path}:{node.lineno}: os.environ access")
        elif (
            isinstance(node, ast.Name)
            and node.id in os_imported_environs
            and isinstance(node.ctx, ast.Load)
        ):
            violations.append(f"{path}:{node.lineno}: os.environ alias access")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "home"
            and (
                (isinstance(node.func.value, ast.Name) and node.func.value.id in path_aliases)
                or (
                    isinstance(node.func.value, ast.Attribute)
                    and isinstance(node.func.value.value, ast.Name)
                    and node.func.value.attr == "Path"
                    and node.func.value.value.id in path_module_aliases
                )
            )
        ):
            violations.append(f"{path}:{node.lineno}: Path.home()")
    return violations


def _domain_runtime_io_violations(tree: ast.AST, path: Path) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "open"
        ):
            violations.append(f"{path}:{node.lineno}: open(...)")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "open"
        ):
            violations.append(f"{path}:{node.lineno}: *.open(...)")
    return violations


def _is_under(path: Path, package: str) -> bool:
    rel = path.relative_to(PACKAGE_ROOT)
    return bool(rel.parts) and rel.parts[0] == package


def test_domain_does_not_import_application_ports_contracts() -> None:
    violations = []
    for path in _python_files():
        if not _is_under(path, "domain"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        violations.extend(_import_violations(tree, path, FORBIDDEN_DOMAIN_IMPORTS, "domain"))
    assert not violations, "Domain layer import violations:\\n" + "\\n".join(violations)


def test_architecture_layer_discovery_is_not_empty() -> None:
    for package in ("domain", "application", "contracts", "ports"):
        matches = [path for path in _python_files() if _is_under(path, package)]
        assert matches, f"architecture layer discovery returned no files for {package}"


def test_application_does_not_import_ledgermind_local() -> None:
    violations = []
    for path in _python_files():
        if not _is_under(path, "application"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        violations.extend(_import_violations(tree, path, {"ledgermind_local"}, "application"))
    assert not violations, (
        "Application layer ledgermind_local import violations:\\n" + "\\n".join(violations)
    )


def test_core_does_not_import_forbidden_external_dependencies() -> None:
    violations = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        violations.extend(_import_violations(tree, path, FORBIDDEN_CORE_IMPORTS, "core"))
    assert not violations, "Core forbidden imports found:\\n" + "\\n".join(violations)


def test_domain_does_not_perform_io() -> None:
    violations = []
    for path in _python_files():
        if not _is_under(path, "domain"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        violations.extend(_domain_runtime_io_violations(tree, path))
    assert not violations, "Domain I/O violations found:\\n" + "\\n".join(violations)


def test_core_does_not_call_path_home() -> None:
    violations = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        violations.extend(_runtime_call_violations(tree, path))
    assert not violations, "Core Path.home() violations:\\n" + "\\n".join(violations)
