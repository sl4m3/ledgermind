"""Ownership-safe lifecycle adapters for command-hook agent clients."""

from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..errors import AdapterError
from ..permissions import ensure_private_dir
from .base import AdapterContext, BaseTargetAdapter, TargetDiscovery


@dataclass(frozen=True, slots=True)
class LifecycleTargetSpec:
    target_id: str
    label: str
    executable: str
    env_home: str
    default_home: tuple[str, ...]
    config_name: str
    events: tuple[tuple[str, str, int], ...]
    format: str = "claude"
    executable_aliases: tuple[str, ...] = ()
    background_events: tuple[str, ...] = ()


SPECS = (
    LifecycleTargetSpec(
        "codex",
        "Codex CLI",
        "codex",
        "CODEX_HOME",
        (".codex",),
        "hooks.json",
        (
            ("UserPromptSubmit", "UserPromptSubmit", 60),
            ("PreToolUse", "PreToolUse", 5),
            ("PostToolUse", "PostToolUse", 5),
            ("Stop", "Stop", 600),
            ("SessionEnd", "SessionEnd", 3),
        ),
        background_events=("Stop",),
    ),
    LifecycleTargetSpec(
        "claude-code",
        "Claude Code",
        "claude",
        "CLAUDE_CONFIG_DIR",
        (".claude",),
        "settings.json",
        (
            ("UserPromptSubmit", "UserPromptSubmit", 60),
            ("PreToolUse", "PreToolUse", 5),
            ("PostToolUse", "PostToolUse", 5),
            ("PostToolUseFailure", "PostToolUseFailure", 5),
            ("Stop", "Stop", 60),
            ("SessionEnd", "SessionEnd", 3),
        ),
    ),
    LifecycleTargetSpec(
        "cursor",
        "Cursor",
        "cursor",
        "CURSOR_HOME",
        (".cursor",),
        "hooks.json",
        (
            ("beforeSubmitPrompt", "UserPromptSubmit", 60),
            ("preToolUse", "PreToolUse", 5),
            ("postToolUse", "PostToolUse", 5),
            ("postToolUseFailure", "PostToolUseFailure", 5),
            ("afterAgentResponse", "afterAgentResponse", 5),
            ("stop", "Stop", 60),
            ("sessionEnd", "SessionEnd", 3),
        ),
        format="cursor",
        executable_aliases=("cursor-agent",),
    ),
)


def _home(spec: LifecycleTargetSpec) -> Path:
    configured = os.environ.get(spec.env_home, "").strip()
    if configured:
        return Path(configured).expanduser()
    if spec.target_id == "opencode":
        xdg_config = os.environ.get("XDG_CONFIG_HOME", "").strip()
        if xdg_config:
            return Path(xdg_config).expanduser() / "opencode"
    return Path.home().joinpath(*spec.default_home)


def _read_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError(f"agent config is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise AdapterError(f"agent config must contain a JSON object: {path}")
    return payload


def _write_object(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _hook_command(
    context: AdapterContext, target: str, event: str, config: Path
) -> str:
    return shlex.join(
        (
            str(context.paths.bin_link),
            "integration-hook",
            "--config",
            str(config),
            "--event",
            event,
        )
    )


def _owned(command: object) -> bool:
    return isinstance(command, str) and " integration-hook " in f" {command} "


def _merge_hooks(
    payload: dict[str, Any],
    spec: LifecycleTargetSpec,
    commands: dict[str, tuple[str, int]],
) -> None:
    hooks = payload.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise AdapterError("agent hooks configuration must be an object")
    if spec.format == "cursor":
        payload.setdefault("version", 1)
        for host_event, (command, timeout) in commands.items():
            entries = hooks.setdefault(host_event, [])
            if not isinstance(entries, list):
                raise AdapterError(f"agent hook {host_event} must be a list")
            entries[:] = [
                entry
                for entry in entries
                if not (isinstance(entry, dict) and _owned(entry.get("command")))
            ]
            handler: dict[str, Any] = {"command": command, "timeout": timeout}
            if host_event in spec.background_events:
                handler["async"] = True
            entries.append(handler)
        return
    for host_event, (command, timeout) in commands.items():
        groups = hooks.setdefault(host_event, [])
        if not isinstance(groups, list):
            raise AdapterError(f"agent hook {host_event} must be a list")
        cleaned: list[Any] = []
        for group in groups:
            if not isinstance(group, dict):
                cleaned.append(group)
                continue
            group_hooks = group.get("hooks")
            if not isinstance(group_hooks, list):
                cleaned.append(group)
                continue
            retained = [
                item
                for item in group_hooks
                if not (isinstance(item, dict) and _owned(item.get("command")))
            ]
            if retained:
                copy = dict(group)
                copy["hooks"] = retained
                cleaned.append(copy)
        handler = {"type": "command", "command": command, "timeout": timeout}
        if host_event in spec.background_events:
            handler["async"] = True
        cleaned.append({"hooks": [handler]})
        hooks[host_event] = cleaned


def _remove_hooks(payload: dict[str, Any]) -> int:
    hooks = payload.get("hooks")
    if not isinstance(hooks, dict):
        return 0
    removed = 0
    for event, entries in tuple(hooks.items()):
        if not isinstance(entries, list):
            continue
        retained: list[Any] = []
        for entry in entries:
            if isinstance(entry, dict) and _owned(entry.get("command")):
                removed += 1
                continue
            if isinstance(entry, dict) and isinstance(entry.get("hooks"), list):
                child = [
                    item
                    for item in entry["hooks"]
                    if not (isinstance(item, dict) and _owned(item.get("command")))
                ]
                removed += len(entry["hooks"]) - len(child)
                if child:
                    copy = dict(entry)
                    copy["hooks"] = child
                    retained.append(copy)
                continue
            retained.append(entry)
        if retained:
            hooks[event] = retained
        else:
            hooks.pop(event, None)
    return removed


class LifecycleTargetAdapter(BaseTargetAdapter):
    def __init__(self, spec: LifecycleTargetSpec) -> None:
        self.spec = spec
        self.id = spec.target_id
        self.label = spec.label

    def discover(self) -> TargetDiscovery:
        home = _home(self.spec).absolute()
        executable = next(
            (
                resolved
                for name in (self.spec.executable, *self.spec.executable_aliases)
                if (resolved := shutil.which(name)) is not None
            ),
            None,
        )
        detected = home.is_dir() or executable is not None
        return TargetDiscovery(
            self.id,
            self.label,
            detected,
            home=home if detected else None,
            config_dir=home if detected else None,
            detail=(
                f"{self.label} discovered"
                if detected
                else f"{self.label} was not found; install {self.spec.executable} first"
            ),
        )

    def _home(self, context: AdapterContext) -> Path:
        discovery = context.discovery or self.discover()
        if not discovery.detected or discovery.home is None:
            raise AdapterError(discovery.detail or f"{self.label} was not discovered")
        return discovery.home

    def _integration_dir(self, context: AdapterContext) -> Path:
        return context.paths.integrations_dir / self.id

    def _config_path(self, context: AdapterContext) -> Path:
        return self._integration_dir(context) / "config.json"

    def _agent_config(self, context: AdapterContext) -> Path:
        return self._home(context) / self.spec.config_name

    def preflight(self, context: AdapterContext) -> dict[str, Any]:
        return {"target": self.id, "discovery": self._discovery(context).as_dict()}

    def _discovery(self, context: AdapterContext) -> TargetDiscovery:
        discovery = context.discovery or self.discover()
        if not discovery.detected:
            raise AdapterError(discovery.detail or f"{self.label} was not discovered")
        return discovery

    def install(self, context: AdapterContext) -> dict[str, Any]:
        target = self._agent_config(context)
        config_path = self._config_path(context)
        if context.dry_run:
            return {
                "status": "dry_run",
                "config": str(config_path),
                "agent_config": str(target),
            }
        ensure_private_dir(self._integration_dir(context))
        previous = _read_object(config_path) if config_path.is_file() else {}
        source_instance_id = previous.get("source_instance_id")
        if not isinstance(source_instance_id, str) or not source_instance_id:
            source_instance_id = f"{self.id}-{uuid4().hex}"
        runtime = {
            "target": self.id,
            "enabled": bool(context.metadata.get("enabled", True)),
            "endpoint": "http://127.0.0.1:8765",
            "token_file": str(context.paths.data_dir / "local" / "server.token"),
            "memory_space_id": context.config.memory_space_id_for(self.id),
            "source_instance_id": source_instance_id,
            "profile_id": "generation-operational",
            "spool_dir": str(self._integration_dir(context) / "spool"),
            "runtime_command": str(context.paths.bin_link),
            "heartbeat_seconds": context.config.runtime.heartbeat_seconds,
            "model_residency_mode": context.config.runtime.residency_mode,
            "session_safety_ttl_seconds": (
                context.config.runtime.session_safety_ttl_seconds
            ),
        }
        _write_object(config_path, runtime)
        payload = _read_object(target)
        commands = {
            host_event: (
                _hook_command(context, self.id, bridge_event, config_path),
                timeout,
            )
            for host_event, bridge_event, timeout in self.spec.events
        }
        _merge_hooks(payload, self.spec, commands)
        _write_object(target, payload)
        _write_object(
            self._integration_dir(context) / "installation-record.json",
            {"schema_version": 1, "target": self.id, "agent_config": str(target)},
        )
        return {
            "status": "passed",
            "config": str(config_path),
            "agent_config": str(target),
            "hooks": sorted(commands),
        }

    def configure(self, context: AdapterContext) -> dict[str, Any]:
        return self.install(context)

    def register_hooks(self, context: AdapterContext) -> dict[str, Any]:
        return self.install(context)

    def verify(self, context: AdapterContext) -> dict[str, Any]:
        config_path = self._config_path(context)
        agent_config = self._agent_config(context)
        if not config_path.is_file() or not agent_config.is_file():
            raise AdapterError(f"{self.label} integration files are missing")
        serialized = json.dumps(_read_object(agent_config), ensure_ascii=False)
        expected = len(self.spec.events)
        actual = serialized.count(" integration-hook ")
        if actual != expected:
            raise AdapterError(
                f"{self.label} requires {expected} LedgerMind hooks, found {actual}"
            )
        result: dict[str, Any] = {"status": "passed", "hooks": actual}
        if self.id == "codex":
            result["activation_required"] = (
                "Review and trust LedgerMind hooks with /hooks"
            )
        return result

    def repair(self, context: AdapterContext) -> dict[str, Any]:
        return self.install(context)

    def uninstall(
        self, context: AdapterContext, *, purge: bool = False
    ) -> dict[str, Any]:
        target = self._agent_config(context)
        removed = 0
        if target.is_file():
            payload = _read_object(target)
            removed = _remove_hooks(payload)
            _write_object(target, payload)
        integration_dir = self._integration_dir(context)
        if purge and integration_dir.exists():
            shutil.rmtree(integration_dir)
        else:
            (integration_dir / "config.json").unlink(missing_ok=True)
            (integration_dir / "installation-record.json").unlink(missing_ok=True)
        return {"status": "passed", "removed_hooks": removed}

    def runtime_environment(self, context: AdapterContext) -> dict[str, str]:
        key = f"LEDGERMIND_{self.id.upper().replace('-', '_')}_CONFIG"
        return {
            key: str(self._config_path(context)),
            "LEDGERMIND_RUNTIME_ENDPOINT": "http://127.0.0.1:8765",
        }


PLUGIN_SPECS = (
    LifecycleTargetSpec(
        "opencode",
        "OpenCode",
        "opencode",
        "OPENCODE_CONFIG_DIR",
        (".config", "opencode"),
        "opencode.json",
        (),
    ),
    LifecycleTargetSpec(
        "openclaw",
        "OpenClaw",
        "openclaw",
        "OPENCLAW_HOME",
        (".openclaw",),
        "openclaw.json",
        (),
    ),
)


class PluginTargetAdapter(LifecycleTargetAdapter):
    """Install a signed local JavaScript plugin and its private bridge config."""

    def _payload(self, context: AdapterContext) -> Path:
        if context.bundle_root is None:
            raise AdapterError(
                f"signed {self.label} payload is missing from platform bundle"
            )
        payload = context.bundle_root / "integrations" / self.id / "plugin"
        if not payload.is_dir():
            raise AdapterError(
                f"signed {self.label} payload is missing from platform bundle"
            )
        return payload

    def _plugin_root(self, context: AdapterContext) -> Path:
        home = self._home(context)
        if self.id == "opencode":
            return home / "plugins"
        return home / "extensions" / "ledgermind-memory"

    def _write_runtime_config(self, context: AdapterContext) -> Path:
        integration_dir = self._integration_dir(context)
        ensure_private_dir(integration_dir)
        path = self._config_path(context)
        previous = _read_object(path) if path.is_file() else {}
        source_instance_id = previous.get("source_instance_id")
        if not isinstance(source_instance_id, str) or not source_instance_id:
            source_instance_id = f"{self.id}-{uuid4().hex}"
        _write_object(
            path,
            {
                "target": self.id,
                "enabled": bool(context.metadata.get("enabled", True)),
                "endpoint": "http://127.0.0.1:8765",
                "token_file": str(context.paths.data_dir / "local" / "server.token"),
                "memory_space_id": context.config.memory_space_id_for(self.id),
                "source_instance_id": source_instance_id,
                "profile_id": "generation-operational",
                "spool_dir": str(integration_dir / "spool"),
                "runtime_command": str(context.paths.bin_link),
                "heartbeat_seconds": context.config.runtime.heartbeat_seconds,
                "model_residency_mode": context.config.runtime.residency_mode,
                "session_safety_ttl_seconds": (
                    context.config.runtime.session_safety_ttl_seconds
                ),
            },
        )
        return path

    @staticmethod
    def _record(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {"exists": False}
        return {
            "exists": True,
            "content": base64.b64encode(path.read_bytes()).decode("ascii"),
            "mode": path.stat().st_mode & 0o777,
        }

    def install(self, context: AdapterContext) -> dict[str, Any]:
        payload = self._payload(context)
        plugin_root = self._plugin_root(context)
        config_path = self._config_path(context)
        if context.dry_run:
            return {
                "status": "dry_run",
                "plugin_root": str(plugin_root),
                "config": str(config_path),
            }
        config_path = self._write_runtime_config(context)
        plugin_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        record_path = self._integration_dir(context) / "installation-record.json"
        previous_record = _read_object(record_path) if record_path.is_file() else {}
        record: dict[str, Any] = {"schema_version": 1, "target": self.id, "files": {}}
        if self.id == "opencode":
            sources = [payload / "ledgermind.js"]
        else:
            sources = [
                payload / name
                for name in ("index.js", "package.json", "openclaw.plugin.json")
            ]
        sources = [path for path in sources if path.is_file()]
        if not sources:
            raise AdapterError(f"signed {self.label} payload is empty")
        for source in sources:
            relative = source.relative_to(payload)
            destination = plugin_root / (
                "ledgermind.js" if self.id == "opencode" else relative
            )
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            before = self._record(destination)
            content = source.read_text(encoding="utf-8")
            content = content.replace(
                "__LEDGERMIND_COMMAND__", str(context.paths.bin_link)
            )
            content = content.replace("__LEDGERMIND_CONFIG__", str(config_path))
            destination.write_text(content, encoding="utf-8")
            os.chmod(destination, 0o600)
            record["files"][str(destination)] = {
                "before": before,
                "after": base64.b64encode(destination.read_bytes()).decode("ascii"),
            }
        if self.id == "openclaw":
            agent_config = self._agent_config(context)
            config = _read_object(agent_config)
            plugins = config.setdefault("plugins", {})
            if not isinstance(plugins, dict):
                raise AdapterError("OpenClaw plugins configuration must be an object")
            entries = plugins.setdefault("entries", {})
            if not isinstance(entries, dict):
                raise AdapterError("OpenClaw plugin entries must be an object")
            owned_entry = {
                "enabled": True,
                "hooks": {
                    "allowConversationAccess": True,
                    "allowPromptInjection": True,
                },
            }
            entries["ledgermind-memory"] = owned_entry
            allowed = plugins.setdefault("allow", [])
            if not isinstance(allowed, list):
                raise AdapterError("OpenClaw plugins.allow must be an array")
            already_allowed = "ledgermind-memory" in allowed
            if not already_allowed:
                allowed.append("ledgermind-memory")
            _write_object(agent_config, config)
            record["openclaw_entry"] = owned_entry
            record["openclaw_allow_added"] = bool(
                previous_record.get("openclaw_allow_added") or not already_allowed
            )
        _write_object(record_path, record)
        return {
            "status": "passed",
            "plugin_root": str(plugin_root),
            "config": str(config_path),
        }

    def verify(self, context: AdapterContext) -> dict[str, Any]:
        root = self._plugin_root(context)
        required = (
            (root / "ledgermind.js",)
            if self.id == "opencode"
            else (
                root / "index.js",
                root / "package.json",
                root / "openclaw.plugin.json",
            )
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing or not self._config_path(context).is_file():
            raise AdapterError(
                f"{self.label} integration files are missing: {', '.join(missing)}"
            )
        return {"status": "passed", "plugin_root": str(root)}

    def uninstall(
        self, context: AdapterContext, *, purge: bool = False
    ) -> dict[str, Any]:
        record_path = self._integration_dir(context) / "installation-record.json"
        record = _read_object(record_path) if record_path.is_file() else {"files": {}}
        restored = 0
        skipped = 0
        if self.id == "openclaw":
            agent_config = self._agent_config(context)
            config = _read_object(agent_config)
            plugins = config.get("plugins")
            entries = plugins.get("entries") if isinstance(plugins, dict) else None
            current = (
                entries.get("ledgermind-memory") if isinstance(entries, dict) else None
            )
            if current == record.get("openclaw_entry"):
                assert isinstance(entries, dict)
                entries.pop("ledgermind-memory", None)
                restored += 1
            elif current is not None:
                skipped += 1
            allowed = plugins.get("allow") if isinstance(plugins, dict) else None
            if (
                record.get("openclaw_allow_added")
                and isinstance(plugins, dict)
                and isinstance(allowed, list)
            ):
                filtered_allow = [
                    item for item in allowed if item != "ledgermind-memory"
                ]
                plugins["allow"] = filtered_allow
                restored += len(allowed) - len(filtered_allow)
            _write_object(agent_config, config)
        for name, details in dict(record.get("files", {})).items():
            path = Path(name)
            if not isinstance(details, dict):
                continue
            expected = base64.b64decode(details.get("after", ""))
            if path.is_file() and path.read_bytes() != expected:
                skipped += 1
                continue
            before = details.get("before", {})
            if isinstance(before, dict) and before.get("exists"):
                path.write_bytes(base64.b64decode(before.get("content", "")))
                os.chmod(path, int(before.get("mode", 0o600)))
            else:
                path.unlink(missing_ok=True)
            restored += 1
        if purge and self._integration_dir(context).exists():
            shutil.rmtree(self._integration_dir(context))
        else:
            self._config_path(context).unlink(missing_ok=True)
            record_path.unlink(missing_ok=True)
        return {
            "status": "passed",
            "restored": restored,
            "skipped_user_changes": skipped,
        }


__all__ = [
    "PLUGIN_SPECS",
    "SPECS",
    "LifecycleTargetAdapter",
    "LifecycleTargetSpec",
    "PluginTargetAdapter",
]
