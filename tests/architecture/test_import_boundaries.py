"""Architecture boundary checks for the core package."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "ledgermind_core"
FORBIDDEN_IMPORTS = {
    "fastapi",
    "uvicorn",
    "sqlite3",
    "sqlalchemy",
    "numpy",
    "annoy",
    "llama_cpp",
    "git",
    "requests",
    "httpx",
    "ledgermind_local",
}


def _python_files() -> list[Path]:
    return [path for path in SRC_ROOT.rglob("*.py")]


def _module_violations(tree: ast.AST, path: Path) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_module = alias.name.split(".")[0]
                if top_module in FORBIDDEN_IMPORTS:
                    violations.append(f"{path}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            top_module = node.module.split(".")[0]
            if top_module in FORBIDDEN_IMPORTS:
                violations.append(f"{path}:{node.lineno}: from {node.module} import ...")
    return violations


def _runtime_call_violations(tree: ast.AST, path: Path) -> list[str]:
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
            and node.func.attr == "home"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "Path"
        ):
            violations.append(f"{path}:{node.lineno}: Path.home()")
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
            and node.attr == "environ"
        ):
            violations.append(f"{path}:{node.lineno}: os.environ")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "subprocess"
        ):
            violations.append(f"{path}:{node.lineno}: subprocess(...)")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ):
            violations.append(
                f"{path}:{node.lineno}: subprocess.{node.func.attr}(...)"
            )
    return violations


def _is_domain_or_application(path: Path) -> bool:
    rel = path.relative_to(SRC_ROOT)
    return "domain" in rel.parts or "application" in rel.parts


def test_core_forbidden_imports_are_absent() -> None:
    violations = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        violations.extend(_module_violations(tree, path))
    assert not violations, "Forbidden imports found:\\n" + "\\n".join(violations)


def test_domain_and_application_do_not_use_file_or_process_boundaries() -> None:
    violations = []
    for path in _python_files():
        if not _is_domain_or_application(path):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        violations.extend(_runtime_call_violations(tree, path))
    assert not violations, "Forbidden runtime boundary usage found:\\n" + "\\n".join(
        violations
    )
