"""Shared operation helpers."""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from ..config_writer import load_installer_config
from ..download import download_artifact
from ..errors import ConfigurationError, TransactionError
from ..manifest import InstallManifest, load_manifest
from ..models import InstallerConfig
from ..paths import InstallerPaths
from ..permissions import ensure_private_dir
from ..preflight import platform_id
from ..verify import verify_artifact_signature, verify_file, verify_manifest_bytes


def config_from_path(path: str | Path | None) -> InstallerConfig:
    if path is None:
        raise ConfigurationError("--config is required for this operation")
    try:
        return load_installer_config(path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigurationError("install config is invalid") from exc


def resolve_manifest(
    path: str | Path | None, bundle_root: str | Path | None
) -> tuple[InstallManifest | None, Path | None]:
    manifest_path: Path | None = Path(path).expanduser() if path else None
    root = Path(bundle_root).expanduser() if bundle_root else None
    if (
        manifest_path is None
        and root is not None
        and (root / "install-manifest.json").is_file()
    ):
        manifest_path = root / "install-manifest.json"
    if manifest_path is None:
        return None, root
    manifest = load_manifest(manifest_path)
    return manifest, root


def fetch_release(
    paths: InstallerPaths, *, public_key: bytes | str | None = None
) -> tuple[Path, Path, Path]:
    """Fetch stable release assets using the signed manifest contract."""

    manifest_path, signature_path, manifest = fetch_manifest(
        paths, public_key=public_key
    )
    bundle_path = fetch_bundle(paths, manifest, public_key=public_key)
    return manifest_path, signature_path, bundle_path


def fetch_manifest(
    paths: InstallerPaths, *, public_key: bytes | str | None = None
) -> tuple[Path, Path, InstallManifest]:
    """Fetch and verify release metadata without downloading the bundle."""

    base_url = os.environ.get("LEDGERMIND_RELEASE_BASE_URL", "").strip()
    if not base_url:
        raise ConfigurationError(
            "LEDGERMIND_RELEASE_BASE_URL is required for network bootstrap"
        )
    base_url = base_url.rstrip("/") + "/"
    manifest_path = paths.downloads_dir / "install-manifest.json"
    signature_path = paths.downloads_dir / "install-manifest.sig"
    download_artifact(urljoin(base_url, "install-manifest.json"), manifest_path)
    download_artifact(urljoin(base_url, "install-manifest.sig"), signature_path)
    manifest = load_manifest(manifest_path)
    verify_manifest_bytes(
        manifest_path.read_bytes(),
        signature_path.read_bytes(),
        public_key=public_key,
    )
    return manifest_path, signature_path, manifest


def fetch_bundle(
    paths: InstallerPaths,
    manifest: InstallManifest,
    *,
    public_key: bytes | str | None = None,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    base_url = os.environ.get("LEDGERMIND_RELEASE_BASE_URL", "").strip()
    if not base_url:
        raise ConfigurationError(
            "LEDGERMIND_RELEASE_BASE_URL is required for bundle download"
        )
    base_url = base_url.rstrip("/") + "/"
    platform = platform_id()
    artifact = manifest.platform(platform).bundle
    bundle_path = paths.downloads_dir / f"ledgermind-{platform}.tar.zst"
    download_artifact(
        urljoin(base_url, artifact.url),
        bundle_path,
        expected_size=artifact.size,
        expected_sha256=artifact.sha256,
        progress=progress,
    )
    verify_file(bundle_path, artifact)
    verify_artifact_signature(bundle_path, artifact, public_key=public_key)
    return bundle_path


def unpack_bundle(source: str | Path, destination: str | Path) -> Path:
    source_path = Path(source).expanduser()
    destination_path = Path(destination).expanduser()
    if source_path.is_dir():
        return source_path
    if not source_path.is_file():
        raise TransactionError(f"bundle artifact does not exist: {source_path}")
    # This path is a reusable download/extraction cache. Leaving files from a
    # previous, larger bundle here makes a later release silently import stale
    # Python modules that are no longer present in the new archive.
    if destination_path.exists():
        shutil.rmtree(destination_path)
    ensure_private_dir(destination_path)
    decompressed: Path | None = None
    try:
        try:
            archive = tarfile.open(source_path, mode="r:*")  # noqa: SIM115
        except tarfile.ReadError:
            if not source_path.name.endswith(".tar.zst"):
                raise
            try:
                import zstandard
            except ImportError as exc:
                raise TransactionError(
                    "zstandard support is missing from the installer runtime"
                ) from exc
            with tempfile.NamedTemporaryFile(
                dir=destination_path.parent, suffix=".tar", delete=False
            ) as handle:
                decompressed = Path(handle.name)
                with source_path.open("rb") as source_handle:
                    zstandard.ZstdDecompressor().copy_stream(source_handle, handle)
            archive = tarfile.open(decompressed, mode="r:")  # noqa: SIM115
        with archive:
            members = archive.getmembers()
            for member in members:
                target = (destination_path / member.name).resolve()
                if (
                    target != destination_path.resolve()
                    and destination_path.resolve() not in target.parents
                ):
                    raise TransactionError("platform bundle contains an unsafe path")
                if member.issym() or member.islnk():
                    link_target = (target.parent / member.linkname).resolve()
                    if destination_path.resolve() not in link_target.parents:
                        raise TransactionError(
                            "platform bundle contains an unsafe link"
                        )
            try:
                archive.extractall(destination_path, filter="data")
            except TypeError:  # Python 3.10/3.11 compatibility
                archive.extractall(destination_path, members=members)
    except (OSError, tarfile.TarError, TypeError) as exc:
        raise TransactionError("cannot unpack platform bundle") from exc
    finally:
        if decompressed is not None:
            decompressed.unlink(missing_ok=True)
    entries = list(destination_path.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return destination_path


def write_install_history(paths: InstallerPaths, event: dict[str, Any]) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with paths.install_history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    os.chmod(paths.install_history, 0o600)


def install_bin_link(paths: InstallerPaths) -> None:
    target = paths.current_link / "bin" / "ledgermind"
    if not target.exists():
        raise TransactionError(f"bundle does not contain executable: {target}")
    paths.bin_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = paths.bin_link.with_name(f".{paths.bin_link.name}.tmp")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target)
    temporary.replace(paths.bin_link)


def remove_bin_link(paths: InstallerPaths) -> None:
    if paths.bin_link.is_symlink() or paths.bin_link.exists():
        paths.bin_link.unlink(missing_ok=True)


def verify_manifest_signature(
    manifest_path: Path, signature_path: Path, public_key: bytes | str | None
) -> None:
    try:
        verify_manifest_bytes(
            manifest_path.read_bytes(),
            signature_path.read_bytes(),
            public_key=public_key,
        )
    except OSError as exc:
        raise ConfigurationError("signed manifest files cannot be read") from exc


def platform_manifest(manifest: InstallManifest) -> Any:
    return manifest.platform(platform_id())


__all__ = [
    "config_from_path",
    "fetch_bundle",
    "fetch_manifest",
    "fetch_release",
    "install_bin_link",
    "platform_manifest",
    "remove_bin_link",
    "resolve_manifest",
    "unpack_bundle",
    "verify_manifest_signature",
    "write_install_history",
]
