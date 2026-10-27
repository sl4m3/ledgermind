"""Post-download and runtime embedding verification."""

from __future__ import annotations

import json
import math
import os
import subprocess
import textwrap
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ..verify import sha256_file


def _checked_model_path(root: Path, value: object) -> Path:
    relative = Path(str(value).replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts or relative == Path("."):
        raise ValueError("model catalog contains an unsafe file path")
    return root / relative


def verify_model_files(model_dir: str | Path, entry: dict[str, Any]) -> dict[str, Any]:
    root = Path(model_dir)
    checked = 0
    expected_files = dict(entry.get("sha256", {}))
    if not expected_files and isinstance(entry.get("files"), list):
        expected_files = {
            str(record.get("name")): record.get("sha256")
            for record in entry["files"]
            if isinstance(record, dict) and record.get("name") and record.get("sha256")
        }
    for name, expected in expected_files.items():
        path = _checked_model_path(root, name)
        if not path.is_file() or sha256_file(path).lower() != str(expected).lower():
            raise ValueError(f"model checksum mismatch: {name}")
        checked += 1
    return {
        "files_checked": checked,
        "license": entry.get("license"),
        "status": "passed",
    }


def run_embedding_smoke(
    embed: Callable[[Sequence[str]], Sequence[Sequence[float]]],
    *,
    dimensions: int,
) -> dict[str, Any]:
    one = [
        tuple(float(value) for value in vector)
        for vector in embed(("LedgerMind smoke",))
    ]
    batch = [
        tuple(float(value) for value in vector)
        for vector in embed(("LedgerMind smoke", "LedgerMind smoke 2"))
    ]
    if len(one) != 1 or len(batch) != 2:
        raise ValueError("embedding smoke returned an invalid batch")
    if any(
        len(vector) != dimensions or not all(math.isfinite(value) for value in vector)
        for vector in (*one, *batch)
    ):
        raise ValueError(
            "embedding smoke returned invalid dimensions or non-finite floats"
        )
    repeat = tuple(float(value) for value in embed(("LedgerMind smoke",))[0])
    deterministic = repeat == one[0]
    if not deterministic:
        raise ValueError("embedding runtime is not deterministic for identical input")
    return {
        "status": "passed",
        "dimensions": dimensions,
        "deterministic": deterministic,
    }


def verify_local_runtime_inference(
    *,
    runtime_path: str | Path,
    model_path: str | Path,
    device: str,
    dimensions: int,
    timeout_seconds: float = 900.0,
) -> dict[str, Any]:
    """Load the signed runtime and execute both retrieval roles once."""

    runtime_python = Path(runtime_path) / "bin" / "python3"
    if not runtime_python.is_file():
        raise ValueError("signed local embedding runtime has no Python executable")
    source_root = Path(__file__).resolve().parents[3]
    packaged_site_packages = source_root.parent / "site-packages"
    script = textwrap.dedent(
        """
        import json
        import sys
        from ledgermind_local.inference.sentence_transformer_vectorizer import SentenceTransformerVectorizer

        vectorizer = SentenceTransformerVectorizer(
            model_path=sys.argv[1],
            device=sys.argv[2],
            expected_dimension=int(sys.argv[3]),
        )
        query = vectorizer.encode(["LedgerMind query smoke"], role="query")
        passage = vectorizer.encode(["LedgerMind passage smoke"], role="passage")
        if len(query) != 1 or len(passage) != 1:
            raise RuntimeError("local embedding runtime returned an invalid batch")
        print(json.dumps({"status": "passed", "dimensions": len(query[0])}))
        vectorizer.close()
        """
    )
    environment = dict(os.environ)
    existing_pythonpath = environment.get("PYTHONPATH", "")
    python_paths = [str(source_root)]
    if packaged_site_packages.is_dir():
        python_paths.append(str(packaged_site_packages))
    if existing_pythonpath:
        python_paths.append(existing_pythonpath)
    environment["PYTHONPATH"] = os.pathsep.join(python_paths)
    try:
        completed = subprocess.run(
            (
                str(runtime_python),
                "-c",
                script,
                str(Path(model_path).expanduser()),
                device,
                str(dimensions),
            ),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=environment,
        )
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise ValueError(
            f"signed local embedding runtime inference smoke failed{suffix}"
        ) from exc
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, IndexError) as exc:
        raise ValueError("signed local embedding runtime inference smoke failed") from exc
    if payload != {"status": "passed", "dimensions": dimensions}:
        raise ValueError(
            "signed local embedding runtime returned invalid smoke metadata"
        )
    return payload


__all__ = [
    "run_embedding_smoke",
    "verify_local_runtime_inference",
    "verify_model_files",
]
