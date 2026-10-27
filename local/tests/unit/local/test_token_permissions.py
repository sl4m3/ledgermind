from __future__ import annotations

import stat
from pathlib import Path

from ledgermind_local.cli import _command_init


def test_token_file_has_private_permissions_on_posix(tmp_path: Path) -> None:
    home = tmp_path / "service"
    home.mkdir()
    exit_code = _command_init(
        __import__("argparse").Namespace(
            home=str(home), force=False, rotate_token=False, semantic_language="ru"
        )
    )
    assert exit_code == 0
    token_file = home / "server.token"
    assert token_file.exists()
    mode = stat.S_IMODE(token_file.stat().st_mode)
    assert mode <= 0o640
