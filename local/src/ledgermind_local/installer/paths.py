"""XDG installation layout for rootless LedgerMind releases."""

from __future__ import annotations

import os
from pathlib import Path


def _xdg(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else default


class InstallerPaths:
    """Resolve all mutable installer paths without requiring root."""

    def __init__(self, *, home_override: str | Path | None = None) -> None:
        home = Path.home()
        self.home_override: Path | None = None
        if home_override is not None:
            root = Path(home_override).expanduser().absolute()
            self.home_override = root
            self.config_home = root / ".config"
            self.data_home = root / ".local" / "share"
            self.state_home = root / ".local" / "state"
            self.cache_home = root / ".cache"
            self.bin_home = root / ".local" / "bin"
        else:
            self.config_home = _xdg("XDG_CONFIG_HOME", home / ".config")
            self.data_home = _xdg("XDG_DATA_HOME", home / ".local" / "share")
            self.state_home = _xdg("XDG_STATE_HOME", home / ".local" / "state")
            self.cache_home = _xdg("XDG_CACHE_HOME", home / ".cache")
            self.bin_home = home / ".local" / "bin"

        self.config_dir = self.config_home / "ledgermind"
        self.data_dir = self.data_home / "ledgermind"
        self.releases_dir = self.data_dir / "releases"
        self.current_link = self.data_dir / "current"
        self.memory_data_dir = self.data_dir / "data"
        self.models_dir = self.data_dir / "models"
        self.integrations_dir = self.data_dir / "integrations"
        self.state_dir = self.state_home / "ledgermind"
        self.runtime_dir = self.state_dir / "runtime"
        self.logs_dir = self.state_dir / "logs"
        self.leases_dir = self.state_dir / "leases"
        self.cache_dir = self.cache_home / "ledgermind"
        self.downloads_dir = self.cache_dir / "downloads"
        self.staging_dir = self.cache_dir / "staging"
        self.config_file = self.config_dir / "config.json"
        self.profiles_file = self.config_dir / "profiles.json"
        self.secrets_file = self.config_dir / "secrets.json"
        self.install_lock = self.state_dir / "install.lock"
        self.install_history = self.state_dir / "install-history.jsonl"
        self.runtime_state = self.runtime_dir / "state.json"
        self.bin_link = self.bin_home / "ledgermind"

    def all_private_dirs(self) -> tuple[Path, ...]:
        return (
            self.config_dir,
            self.data_dir,
            self.releases_dir,
            self.memory_data_dir,
            self.models_dir,
            self.integrations_dir,
            self.state_dir,
            self.runtime_dir,
            self.logs_dir,
            self.leases_dir,
            self.cache_dir,
            self.downloads_dir,
            self.staging_dir,
        )

    def ensure(self) -> None:
        for path in self.all_private_dirs():
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(path, 0o700)

    def release_dir(self, release_version: str) -> Path:
        if not release_version or "/" in release_version or "\\" in release_version:
            raise ValueError("invalid release version")
        return self.releases_dir / release_version

    def as_dict(self) -> dict[str, str]:
        return {
            "config_dir": str(self.config_dir),
            "data_dir": str(self.data_dir),
            "current": str(self.current_link),
            "state_dir": str(self.state_dir),
            "runtime_dir": str(self.runtime_dir),
            "cache_dir": str(self.cache_dir),
            "bin_link": str(self.bin_link),
        }


__all__ = ["InstallerPaths"]
