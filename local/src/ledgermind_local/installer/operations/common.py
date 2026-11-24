"""Shared operation helpers."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from ..config_writer import load_installer_config
from ..download import download_artifact
from ..errors import ConfigurationError, InstallerError, TransactionError
from ..manifest import ArtifactRecord, InstallManifest, load_manifest
from ..models import InstallerConfig
from ..paths import InstallerPaths
from ..permissions import ensure_private_dir
from ..preflight import platform_id
from ..provider_profiles import normalize_reasoning_effort
from ..verify import (
    verify_artifact_signature,
    verify_bundle_tree,
    verify_file,
    verify_manifest_bytes,
)

DEFAULT_RELEASE_BASE_URL = (
    "https://github.com/sl4m3/ledgermind/releases/latest/download"
)
DEFAULT_RELEASE_TAG_BASE_URL = "https://github.com/sl4m3/ledgermind/releases/download"
LAYERED_RUNTIME_PREFIXES = ("embedding-runtimes/", "python/runtime/")


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


def resolve_release_base_url(*, version: str | None = None) -> str:
    """Resolve release download base URL from environment or default GitHub channel."""

    override = os.environ.get("LEDGERMIND_RELEASE_BASE_URL", "").strip()
    if override:
        return override.rstrip("/") + "/"
    if version is not None and version.strip():
        clean = version.strip().removeprefix("v")
        return f"{DEFAULT_RELEASE_TAG_BASE_URL}/v{clean}/"
    return f"{DEFAULT_RELEASE_BASE_URL}/"


def fetch_release(
    paths: InstallerPaths,
    *,
    public_key: bytes | str | None = None,
    version: str | None = None,
    progress: Callable[[int, int | None], None] | None = None,
) -> tuple[Path, Path, Path]:
    """Fetch stable release assets using the signed manifest contract."""

    manifest_path, signature_path, manifest = fetch_manifest(
        paths, public_key=public_key, version=version
    )
    bundle_path = fetch_bundle(
        paths,
        manifest,
        public_key=public_key,
        version=version,
        progress=progress,
    )
    return manifest_path, signature_path, bundle_path


def fetch_manifest(
    paths: InstallerPaths,
    *,
    public_key: bytes | str | None = None,
    version: str | None = None,
) -> tuple[Path, Path, InstallManifest]:
    """Fetch and verify release metadata without downloading the bundle."""

    base_url = resolve_release_base_url(version=version)
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
    version: str | None = None,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    base_url = resolve_release_base_url(version=version)
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


def with_probed_generation_settings(
    config: InstallerConfig, probe_result: Mapping[str, Any]
) -> InstallerConfig:
    """Persist probe-detected mandatory reasoning settings onto InstallerConfig."""

    detected = normalize_reasoning_effort(probe_result.get("reasoning_effort"))
    if (
        detected is None
        or config.generation.reasoning_effort is not None
        or detected == "none"
    ):
        return config
    return config.model_copy(
        update={
            "generation": config.generation.model_copy(
                update={"reasoning_effort": detected}
            )
        }
    )


def installed_release_version(paths: InstallerPaths) -> str | None:
    """Return the currently active release version, if installed."""

    if not paths.current_link.exists():
        return None
    bundle_manifest = paths.current_link / "bundle-manifest.json"
    if bundle_manifest.is_file():
        try:
            payload = json.loads(bundle_manifest.read_text(encoding="utf-8"))
            version = payload.get("release_version")
            if isinstance(version, str) and version.strip():
                return version.strip()
        except (OSError, ValueError):
            pass
    try:
        return paths.current_link.resolve().name
    except OSError:
        return None


def compute_runtime_layer_digest(bundle_manifest_path: str | Path) -> str | None:
    """Compute a stable SHA-256 fingerprint over immutable runtime layer entries."""

    path = Path(bundle_manifest_path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        artifacts = payload.get("artifacts")
    except (OSError, ValueError):
        return None
    if not isinstance(artifacts, dict):
        return None
    rows: list[str] = []
    for rel, record in sorted(artifacts.items()):
        rel_str = str(rel)
        if not rel_str.startswith(LAYERED_RUNTIME_PREFIXES):
            continue
        if not isinstance(record, dict):
            return None
        size = record.get("size")
        sha = record.get("sha256")
        if not isinstance(size, int) or not isinstance(sha, str):
            return None
        rows.append(f"{rel_str}\t{size}\t{sha.lower()}\n")
    if not rows:
        return None
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row.encode("utf-8"))
    return digest.hexdigest()


def layered_patch_record(
    manifest: InstallManifest, *, platform: str | None = None
) -> tuple[ArtifactRecord, str] | None:
    """Return ``(patch_artifact, expected_base_runtime_sha256)`` when offered."""

    layered = manifest.components.get("layered_update")
    if not isinstance(layered, dict):
        return None
    plat = platform or platform_id()
    entry = layered.get(plat)
    if not isinstance(entry, dict):
        return None
    base_sha = entry.get("base_runtime_sha256")
    raw_patch = entry.get("patch")
    if not isinstance(base_sha, str) or not base_sha.strip() or not isinstance(raw_patch, dict):
        return None
    try:
        patch_artifact = ArtifactRecord.model_validate(raw_patch)
    except ValueError:
        return None
    return patch_artifact, base_sha.strip().lower()


def hardlink_or_copy(src: str | Path, dst: str | Path) -> str:
    """Hardlink regular files when on the same filesystem, falling back to copy."""

    src_path = Path(src)
    dst_path = Path(dst)
    if src_path.is_file() and not src_path.is_symlink():
        try:
            if dst_path.exists():
                dst_path.unlink()
            os.link(src_path, dst_path)
            return str(dst_path)
        except OSError:
            pass
    shutil.copy2(src_path, dst_path)
    return str(dst_path)


def assemble_layered_bundle(
    *,
    paths: InstallerPaths,
    manifest: InstallManifest,
    current_release: Path,
    public_key: bytes | str | None = None,
    version: str | None = None,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path | None:
    """Try assembling a verified candidate release from a small patch + local runtime."""

    plat = platform_id()
    patch_info = layered_patch_record(manifest, platform=plat)
    if patch_info is None:
        return None
    patch_artifact, expected_base_sha = patch_info
    actual_base_sha = compute_runtime_layer_digest(
        current_release / "bundle-manifest.json"
    )
    if actual_base_sha != expected_base_sha:
        return None
    layer_dirs = (
        ("embedding-runtimes", current_release / "embedding-runtimes"),
        ("python/runtime", current_release / "python" / "runtime"),
    )
    if not all(src_dir.is_dir() for _, src_dir in layer_dirs):
        return None

    base_url = resolve_release_base_url(version=version)
    patch_path = paths.downloads_dir / f"ledgermind-patch-{plat}.tar.zst"
    staged_dir = paths.staging_dir / "bundle-layered"
    try:
        download_artifact(
            urljoin(base_url, patch_artifact.url),
            patch_path,
            expected_size=patch_artifact.size,
            expected_sha256=patch_artifact.sha256,
            progress=progress,
        )
        verify_file(patch_path, patch_artifact)
        verify_artifact_signature(patch_path, patch_artifact, public_key=public_key)
        bundle_root = unpack_bundle(patch_path, staged_dir)
        for rel_dir, src_dir in layer_dirs:
            dst_dir = bundle_root / rel_dir
            shutil.copytree(
                src_dir,
                dst_dir,
                symlinks=True,
                copy_function=hardlink_or_copy,
                dirs_exist_ok=True,
            )
        verify_bundle_tree(bundle_root, public_key=public_key)
        return bundle_root
    except (InstallerError, OSError):
        shutil.rmtree(staged_dir, ignore_errors=True)
        return None


def prune_old_releases(
    paths: InstallerPaths,
    *,
    keep: int = 2,
    protect: Sequence[Path] = (),
) -> list[str]:
    """Keep the active release and newest backups, pruning older releases."""

    if not paths.releases_dir.is_dir():
        return []
    keep_count = max(int(keep), 1)
    protected: set[Path] = set()
    if paths.current_link.exists():
        try:
            protected.add(paths.current_link.resolve())
        except OSError:
            pass
    for item in protect:
        try:
            protected.add(Path(item).resolve())
        except OSError:
            pass
    candidates: list[tuple[float, Path]] = []
    for entry in paths.releases_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        try:
            resolved = entry.resolve()
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        candidates.append((mtime, resolved))
    candidates.sort(key=lambda item: item[0], reverse=True)
    for _, resolved in candidates[:keep_count]:
        protected.add(resolved)
    pruned: list[str] = []
    for _, resolved in candidates:
        if resolved in protected:
            continue
        shutil.rmtree(resolved, ignore_errors=True)
        pruned.append(resolved.name)
    return pruned


def _update_cache_path(paths: InstallerPaths) -> Path:
    return paths.state_dir / "update-check.json"


def read_update_check_cache(
    paths: InstallerPaths, *, ttl_seconds: float = 86_400.0
) -> dict[str, Any] | None:
    if os.environ.get("LEDGERMIND_NO_UPDATE_CHECK", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        return None
    cache_path = _update_cache_path(paths)
    if not cache_path.is_file():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    checked_at = payload.get("checked_at")
    if (
        isinstance(checked_at, (int, float))
        and not isinstance(checked_at, bool)
        and time.time() - float(checked_at) > ttl_seconds
    ):
        return None
    return payload


def format_transfer_progress(label: str, transferred: int, total: int | None) -> str:
    """Format a compact single-line terminal download progress indicator."""

    transferred_mib = transferred / (1024 * 1024)
    if total is None or total <= 0:
        return f"{label} · {transferred_mib:.1f} MiB"
    total_mib = total / (1024 * 1024)
    percent = min(100, transferred * 100 // total)
    width = 20
    filled = percent * width // 100
    bar = "━" * filled + "─" * (width - filled)
    return f"{label}  {bar}  {percent:3d}%  {transferred_mib:.1f}/{total_mib:.1f} MiB"


def write_update_check_cache(paths: InstallerPaths, payload: dict[str, Any]) -> None:
    paths.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache_path = _update_cache_path(paths)
    record = {"checked_at": time.time(), **payload}
    cache_path.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.chmod(cache_path, 0o600)


__all__ = [
    "DEFAULT_RELEASE_BASE_URL",
    "DEFAULT_RELEASE_TAG_BASE_URL",
    "LAYERED_RUNTIME_PREFIXES",
    "assemble_layered_bundle",
    "compute_runtime_layer_digest",
    "config_from_path",
    "fetch_bundle",
    "fetch_manifest",
    "fetch_release",
    "format_transfer_progress",
    "hardlink_or_copy",
    "install_bin_link",
    "installed_release_version",
    "layered_patch_record",
    "platform_manifest",
    "prune_old_releases",
    "read_update_check_cache",
    "remove_bin_link",
    "resolve_manifest",
    "resolve_release_base_url",
    "unpack_bundle",
    "verify_manifest_signature",
    "with_probed_generation_settings",
    "write_install_history",
    "write_update_check_cache",
]
