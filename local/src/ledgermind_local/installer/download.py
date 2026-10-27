"""Offline-friendly, atomic artifact downloads."""

from __future__ import annotations

import os
import tempfile
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .errors import DownloadError
from .installer_types import DownloadedArtifact
from .verify import sha256_file


def _source_path(url: str) -> Path | None:
    if url.startswith("file://"):
        from urllib.parse import unquote, urlparse

        return Path(unquote(urlparse(url).path)).expanduser()
    candidate = Path(url).expanduser()
    return candidate if candidate.exists() else None


def download_artifact(
    url: str,
    destination: str | Path,
    *,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
    progress: Callable[[int, int | None], None] | None = None,
) -> DownloadedArtifact:
    target = Path(destination).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=f".{target.name}.", suffix=".part", delete=False
        ) as handle:
            temporary = Path(handle.name)
            source = _source_path(url)
            if progress is not None:
                progress(0, expected_size)
            if source is not None:
                source_handle = source.open("rb")
                response_size = source.stat().st_size
            else:
                source_handle = urllib.request.urlopen(url, timeout=60)
                raw_length = source_handle.headers.get("content-length")
                response_size = int(raw_length) if raw_length else None
            total = expected_size if expected_size is not None else response_size
            transferred = 0
            with source_handle:
                while chunk := source_handle.read(1024 * 1024):
                    handle.write(chunk)
                    transferred += len(chunk)
                    if progress is not None:
                        progress(transferred, total)
            handle.flush()
            os.fsync(handle.fileno())
        if expected_size is not None and temporary.stat().st_size != expected_size:
            raise DownloadError("downloaded artifact size does not match manifest")
        digest = sha256_file(temporary)
        if expected_sha256 is not None and digest.lower() != expected_sha256.lower():
            raise DownloadError("downloaded artifact SHA-256 does not match manifest")
        temporary.replace(target)
        return DownloadedArtifact(
            path=target, size=target.stat().st_size, sha256=digest
        )
    except DownloadError:
        raise
    except (OSError, ValueError, TimeoutError) as exc:
        raise DownloadError(f"failed to download artifact: {url}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


__all__ = ["download_artifact"]
