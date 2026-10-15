from pathlib import Path


def test_openclaw_only_resets_after_actual_compaction() -> None:
    asset = (
        Path(__file__).parents[2]
        / "src/ledgermind_integrations/adapters/openclaw/index.js"
    ).read_text(encoding="utf-8")
    assert 'api.on("after_compaction"' in asset
    assert "event.compactedCount > 0" in asset
    assert 'bridge("SessionReset"' in asset
