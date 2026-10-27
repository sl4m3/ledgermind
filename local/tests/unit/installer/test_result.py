from __future__ import annotations

import json
from pathlib import Path

from ledgermind_local.installer.result import InstallResult, ResultStep


def test_result_serializes_nested_paths() -> None:
    result = InstallResult("update")
    result.paths["release"] = Path("/tmp/release")
    result.steps.append(
        ResultStep(
            "update",
            "passed",
            data={"runtime": {"model_path": Path("/tmp/model")}},
        )
    )

    payload = json.loads(result.to_json())

    assert payload["paths"]["release"] == "/tmp/release"
    assert payload["steps"][0]["data"]["runtime"]["model_path"] == "/tmp/model"
