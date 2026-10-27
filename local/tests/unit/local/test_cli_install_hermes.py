"""The Local CLI must not install client integrations."""

from __future__ import annotations

import pytest

from ledgermind_local import cli


def test_local_parser_rejects_removed_hermes_installer() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli._build_parser().parse_args(["install", "hermes"])

    assert exc_info.value.code == 2
