from __future__ import annotations


def test_truncates_at_word_boundary() -> None:
    from ledgermind_local.api.context import _truncate_context_query

    assert _truncate_context_query("Session says beta.", 13) == "Session says"


def test_zero_limit_disables_truncation() -> None:
    from ledgermind_local.api.context import _truncate_context_query

    text = "Session says beta."
    assert _truncate_context_query(text, 0) == text


def test_does_not_cut_inside_backticked_identifier() -> None:
    from ledgermind_local.api.context import _truncate_context_query

    text = "Карточка 280 → 340px, `margin-left: -130px` для центрирования."
    truncated = _truncate_context_query(text, 40)

    assert truncated.count("`") % 2 == 0
    assert "`margin-left: -130px`" not in truncated
    assert "`margin-left:" not in truncated
    assert truncated == "Карточка 280 → 340px,"


def test_returns_empty_when_no_boundary_fits() -> None:
    from ledgermind_local.api.context import _truncate_context_query

    assert _truncate_context_query("supercalifragilistic", 5) == ""


