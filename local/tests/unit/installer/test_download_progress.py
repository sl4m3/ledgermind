from __future__ import annotations

import hashlib
from pathlib import Path

from ledgermind_local.installer.download import download_artifact


def test_download_artifact_reports_determinate_byte_progress(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"x" * (2 * 1024 * 1024 + 17))
    destination = tmp_path / "destination.bin"
    updates: list[tuple[int, int | None]] = []

    result = download_artifact(
        str(source),
        destination,
        expected_size=source.stat().st_size,
        expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        progress=lambda transferred, total: updates.append((transferred, total)),
    )

    assert updates[0] == (0, source.stat().st_size)
    assert updates[-1] == (source.stat().st_size, source.stat().st_size)
    assert [transferred for transferred, _total in updates] == sorted(
        transferred for transferred, _total in updates
    )
    assert result.path == destination
