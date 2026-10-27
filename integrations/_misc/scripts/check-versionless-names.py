#!/usr/bin/env python3
"""Fail when tracked Integrations paths or contents use versioned product names."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
GATE_PATHS = frozenset(
    {
        "scripts/check-versionless-names.py",
        "python/tests/packaging/test_versionless_names.py",
    }
)
METADATA_PATHS = frozenset(
    {"python/pyproject.toml", "protocol/python/pyproject.toml"}
)
MIGRATION_COMPAT_PATHS = frozenset(
    {
        "python/src/ledgermind_integrations/runtime/spool_migration.py",
        "python/tests/test_spool_migration.py",
    }
)
MIGRATION_COMPATIBILITY_VALUES = {
    "python/src/ledgermind_integrations/runtime/spool_migration.py": frozenset(
        {"ledgermind_context_v1"}
    ),
    "python/tests/test_spool_migration.py": frozenset({"ledgermind_context_v1"}),
}
PORCELAIN_PATHS = frozenset({"scripts/release-integrations.py"})
SEMANTIC_CONTRACT_PATHS = frozenset({
    "protocol/python/src/ledgermind_protocol/object_facet.py",
    "protocol/python/src/ledgermind_protocol/context.py",
    "protocol/python/tests/test_semantic_delivery.py",
    "schemas/core-ipc/object-facet/semantic-retrieval-request.schema.json",
    "schemas/core-ipc/object-facet/semantic-retrieval-response.schema.json",
    "schemas/core-ipc/object-facet/scoped-semantic-retrieval-response.schema.json",
})

_TOKEN_RE = re.compile(
    r"(?P<hyphen>-v[0-9]+)"
    r"|(?P<underscore>_v[0-9]+)"
    r"|(?P<camel>V[0-9]+)"
    r"|(?P<bare>(?<![A-Za-z0-9])v[0-9]+)"
)
_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_VERSION_FIELD_RE = re.compile(
    r"(?<![A-Za-z0-9_])[\"']?(?:schema_version|protocol_version|knowledge_schema_version|"
    r"normalizer_version|facet_catalogue_version|facet_catalogue_schema_version|"
    r"embedding_model_version|manifest_schema_version|source_schema_version)[\"']?"
    r"(?![A-Za-z0-9_])\s*[:=]\s*"
)
_VERSION_FIELD_PATH_SUFFIXES = frozenset(
    {".json", ".py", ".rs", ".sql", ".toml", ".yaml", ".yml"}
)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})


@dataclass(frozen=True, slots=True)
class Violation:
    path: str
    line: int
    column: int
    token: str
    token_form: str
    category: str
    source: str


def _tracked_paths(root: Path) -> tuple[Path, ...]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        details = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git ls-files failed: {details}")
    names = result.stdout.split(b"\0")
    return tuple(Path(name.decode("utf-8")) for name in names if name)


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _token_form(match: re.Match[str]) -> str:
    if match.lastgroup == "hyphen":
        return "-v<number>"
    if match.lastgroup == "underscore":
        return "_v<number>"
    if match.lastgroup == "camel":
        return "V<number>"
    return "v<number>"


def _toml_sections(lines: list[str]) -> dict[int, str]:
    current = ""
    sections: dict[int, str] = {}
    for index, line in enumerate(lines):
        header = re.match(r"^\s*\[([^\]]+)\]\s*$", line)
        if header:
            current = header.group(1)
        sections[index] = current
    return sections


def _is_metadata_version_line(path: str, line: str, section: str) -> bool:
    if path not in METADATA_PATHS or not re.match(r"^\s*version\s*=", line):
        return False
    if path.endswith("Cargo.toml"):
        return section in {"package", "workspace.package"}
    return section == "project"


def _is_sql_migration_path(path: str) -> bool:
    parts = path.split("/")
    return (
        path.endswith(".sql")
        and any(part in {"migrations", "rounds_migrations"} for part in parts)
        and re.match(r"^[0-9]+_[^/]+\.sql$", parts[-1]) is not None
    )


def _is_migration_compatibility_module(path: str) -> bool:
    return path in MIGRATION_COMPAT_PATHS


def _is_migration_compatibility_value(path: str, line: str, start: int) -> bool:
    return any(
        match.start() <= start < match.end()
        for value in MIGRATION_COMPATIBILITY_VALUES.get(path, ())
        for match in re.finditer(
            rf"(?<![A-Za-z0-9_]){re.escape(value)}(?![A-Za-z0-9_])", line
        )
    )


def _is_explicit_version_value(path: str, line: str, start: int) -> bool:
    if Path(path).suffix not in _VERSION_FIELD_PATH_SUFFIXES:
        return False
    for prefix in _VERSION_FIELD_RE.finditer(line):
        if start < prefix.end():
            continue
        cursor = prefix.end()
        while cursor < len(line) and line[cursor].isspace():
            cursor += 1
        if cursor >= len(line):
            continue
        if line[cursor] in {"\"", "'"}:
            quote = line[cursor]
            stop = line.find(quote, cursor + 1)
            if stop >= 0 and cursor < start < stop:
                return True
            continue
        value = re.match(r"[^,}\s]+", line[cursor:])
        if value is not None and cursor <= start < cursor + value.end():
            return True
    return False


def _is_external_provider_url(line: str, start: int, end: int) -> bool:
    token = line[start:end]
    if re.fullmatch(r"v[0-9]+", token) is None:
        return False
    for url in _URL_RE.finditer(line):
        raw = url.group(0).rstrip(".,;:)]}")
        relative_start = start - url.start()
        relative_end = end - url.start()
        if relative_start < 0 or relative_end > len(raw):
            continue
        if relative_start == 0 or raw[relative_start - 1] != "/":
            continue
        host = (urlsplit(raw).hostname or "").lower()
        if not host or host in _LOCAL_HOSTS or host.endswith(".localhost"):
            continue
        if host in {"ledgermind.dev", "www.ledgermind.dev"}:
            continue
        return True
    return False


def _is_uuid_v4(path: str, line: str, token: str) -> bool:
    if token != "_v4" or not path.startswith("crates/") or not path.endswith(".rs"):
        return False
    return re.search(r"\b(?:uuid::)?Uuid::new_v4\s*\(", line) is not None


def _is_uuid_feature(path: str, line: str, token: str) -> bool:
    return False


def _is_git_porcelain(path: str, line: str, token: str) -> bool:
    return path in PORCELAIN_PATHS and token == "v1" and "--porcelain=v1" in line


def _allowed(
    path: str,
    line: str,
    start: int,
    token: str,
    source: str,
    section: str,
) -> bool:
    # Versioned transport contracts are not product/release names. Exact values
    # only: arbitrary product-vN and unknown contract versions remain rejected.
    if source == "content" and path in SEMANTIC_CONTRACT_PATHS:
        for literal in re.finditer(
            r'''["'](?:semantic_units_v2|semantic_units_v3|memory_semantics_v2|registered_dependency_scopes_v1)["']''',
            line,
        ):
            if literal.start() < start < literal.end():
                return True
    if source == "path":
        return _is_sql_migration_path(path) or _is_migration_compatibility_module(path)
    if _is_migration_compatibility_value(path, line, start):
        return True
    if _is_metadata_version_line(path, line, section):
        return True
    if _is_explicit_version_value(path, line, start):
        return True
    if _is_uuid_v4(path, line, token) or _is_uuid_feature(path, line, token):
        return True
    if _is_git_porcelain(path, line, token):
        return True
    return _is_external_provider_url(line, start, start + len(token))


def _category(path: str, line: str) -> str:
    context = f"{path} {line}".lower()
    if "manifest" in context and ("format" in context or "manifest" in path.lower()):
        return "versioned-manifest-format"
    if "operation" in context:
        return "versioned-operation"
    if "capabilit" in context:
        return "versioned-capability"
    if "route" in context or "router" in context or re.search(r"[\"']/(?:v[0-9]+)", line):
        return "versioned-route"
    if "extension" in context:
        return "versioned-extension"
    return "product-version-token"


def scan(root: Path = ROOT) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    for relative in _tracked_paths(root):
        path = relative.as_posix()
        if path in GATE_PATHS:
            continue

        for match in _TOKEN_RE.finditer(path):
            token = match.group(0)
            if not _allowed(path, "", match.start(), token, "path", ""):
                violations.append(
                    Violation(
                        path=path,
                        line=0,
                        column=match.start() + 1,
                        token=token,
                        token_form=_token_form(match),
                        category=_category(path, ""),
                        source="path",
                    )
                )

        text = _read_text(root / relative)
        if text is None:
            continue
        lines = text.splitlines()
        sections = _toml_sections(lines)
        for line_number, line in enumerate(lines, start=1):
            for match in _TOKEN_RE.finditer(line):
                token = match.group(0)
                if _allowed(
                    path,
                    line,
                    match.start(),
                    token,
                    "content",
                    sections.get(line_number - 1, ""),
                ):
                    continue
                violations.append(
                    Violation(
                        path=path,
                        line=line_number,
                        column=match.start() + 1,
                        token=token,
                        token_form=_token_form(match),
                        category=_category(path, line),
                        source="content",
                    )
                )
    return tuple(
        sorted(
            violations,
            key=lambda item: (item.path, item.line, item.column, item.source, item.token),
        )
    )


def format_violation(violation: Violation) -> str:
    return (
        f"{violation.path}:{violation.line}:{violation.column}: "
        f"{violation.category}: {violation.token} ({violation.source})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="checkout to inspect")
    args = parser.parse_args(argv)
    try:
        violations = scan(args.root.resolve())
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"versionless-name gate failed: {error}", file=sys.stderr)
        return 2

    if not violations:
        print("versionless-name gate: clean")
        return 0
    print(f"versionless-name gate: {len(violations)} violation(s)")
    for violation in violations:
        print(format_violation(violation))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
