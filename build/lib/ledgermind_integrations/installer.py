"""Install the complete LedgerMind Hermes plugin directory."""

from __future__ import annotations

import base64
import json
import os
from importlib.resources import files
from pathlib import Path
from uuid import uuid4

_PLUGIN_INIT = 'from ledgermind_integrations.adapters.hermes.plugin_entry import register\n\n__all__ = ["register"]\n'


def _write_private(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            temporary.chmod(0o600)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _default_config() -> dict[str, object]:
    hermes_home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
    return {
        "endpoint": "http://127.0.0.1:8765",
        "token_file": "~/.ledgermind/local/server.token",
        "memory_space_id": "project-main",
        "source_instance_id": f"hermes-{uuid4().hex}",
        "profile_id": "default",
        "state_db_path": str(hermes_home / "state.db"),
        "spool_dir": "~/.ledgermind/integrations/hermes",
    }


def _plugin_root(destination: str | Path | None) -> Path:
    plugin_root = (
        Path(destination).expanduser()
        if destination is not None
        else Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser() / "plugins"
    )
    return plugin_root / "ledgermind-hermes"


def install_hermes(destination: str | Path | None = None) -> Path:
    root = _plugin_root(destination)
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root.chmod(0o700)
        files_record: dict[str, object] = {}
        record: dict[str, object] = {
            "schema_version": 1,
            "target": "hermes",
            "files": files_record,
        }

        def remember(path: Path, content: bytes, mode: int = 0o600) -> None:
            before: dict[str, object]
            if path.is_file():
                before = {
                    "exists": True,
                    "mode": path.stat().st_mode & 0o777,
                    "content": base64.b64encode(path.read_bytes()).decode("ascii"),
                }
            else:
                before = {"exists": False}
            files_record[path.name] = {
                "before": before,
                "after": {"content": base64.b64encode(content).decode("ascii")},
            }
            _write_private(path, content)
            path.chmod(mode)

        source = files("ledgermind_integrations.adapters.hermes").joinpath("plugin.yaml")
        plugin_yaml = root / "plugin.yaml"
        with source.open("rb") as source_handle:
            remember(plugin_yaml, source_handle.read())
        remember(root / "__init__.py", _PLUGIN_INIT.encode("utf-8"))
        config = (
            json.dumps(_default_config(), ensure_ascii=False, indent=2, sort_keys=True).encode(
                "utf-8"
            )
            + b"\n"
        )
        remember(root / "config.json", config)
        record_path = root / "installation-record.json"
        record_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        record_path.chmod(0o600)
    except OSError as exc:
        raise RuntimeError("cannot install private Hermes plugin files") from exc
    return plugin_yaml


def uninstall_hermes(destination: str | Path | None = None) -> bool:
    root = _plugin_root(destination)
    if not root.exists():
        return False
    if not root.is_dir():
        raise RuntimeError(f"Hermes plugin path is not a directory: {root}")
    record_path = root / "installation-record.json"
    if record_path.is_file():
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("Hermes installation record is invalid") from exc
        removed = False
        for name, details in dict(record.get("files", {})).items():
            path = root / name
            after = details.get("after", {}) if isinstance(details, dict) else {}
            expected = (
                base64.b64decode(after.get("content", ""))
                if isinstance(after, dict) and after.get("content")
                else None
            )
            if expected is not None and path.is_file() and path.read_bytes() != expected:
                continue
            before = details.get("before", {}) if isinstance(details, dict) else {}
            if isinstance(before, dict) and before.get("exists"):
                path.write_bytes(base64.b64decode(str(before.get("content", ""))))
                path.chmod(int(before.get("mode", 0o600)))
            else:
                path.unlink(missing_ok=True)
            removed = True
        record_path.unlink(missing_ok=True)
        try:
            root.rmdir()
        except OSError:
            pass
        return removed

    removed = False
    for name in ("plugin.yaml", "__init__.py", "config.json"):
        path = root / name
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise RuntimeError("cannot uninstall private Hermes plugin files") from exc
        removed = True
    try:
        root.rmdir()
    except OSError:
        pass
    return removed


__all__ = ["install_hermes", "uninstall_hermes"]
