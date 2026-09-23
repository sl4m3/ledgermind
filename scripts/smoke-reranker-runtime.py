#!/usr/bin/env python3
"""One offline inference with a separately installed reranker runtime."""

from __future__ import annotations

import argparse
import json
import time

from ledgermind_local.inference.retrieval_reranker import QwenWorkerReranker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--documents", type=int, default=1)
    args = parser.parse_args()
    worker = QwenWorkerReranker(
        args.model, "cpu", runtime_path=args.runtime,
        startup_timeout=120, score_timeout=180,
    )
    started = time.monotonic()
    try:
        scores = worker.score(
            "How should the deployment be validated?",
            ["object: Deployment\nfacet: procedure\ncontent: Run checks before release."]
            * args.documents,
        )
    finally:
        worker.close()
    print(json.dumps({"documents": len(scores), "seconds": round(time.monotonic() - started, 3),
                      "first_score": scores[0]}))


if __name__ == "__main__":
    main()
