"""Transport-boundary checks for the transitional Python Core package."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = ROOT / "src" / "ledgermind_core"
FORBIDDEN_TRANSPORT_TERMS = (
    "RawRound",
    "raw_round",
    "Hermes",
    "tool_call",
    "source.event_ids",
)


def test_core_source_contains_no_raw_round_transport_contract() -> None:
    violations = [
        f"{path}:{term}"
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        for term in FORBIDDEN_TRANSPORT_TERMS
        if term in path.read_text(encoding="utf-8")
    ]
    assert not violations, "Core transport terms found:\n" + "\n".join(violations)
