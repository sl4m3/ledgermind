#!/usr/bin/env python3
"""Verify a signed release and database backups without starting inference."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from pathlib import Path

from ledgermind_local.core_gateway.supervisor import CoreSupervisor
from ledgermind_local.installer.verify import verify_bundle_tree
from ledgermind_local.persistence.rounds_migrations import apply_migrations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--trusted-public-key", type=Path, required=True)
    parser.add_argument("--knowledge-backup", type=Path, required=True)
    parser.add_argument("--rounds-backup", type=Path, required=True)
    args = parser.parse_args()
    delivery = verify_bundle_tree(
        args.bundle, public_key=args.trusted_public_key.read_bytes()
    )
    result = {"delivery": delivery, "databases": {}, "provider_calls": 0}
    with tempfile.TemporaryDirectory(prefix="ledgermind-decision-verify-") as directory:
        root = Path(directory)
        for name, backup in (
            ("knowledge", args.knowledge_backup),
            ("rounds", args.rounds_backup),
        ):
            target = root / f"{name}.db"
            with (
                sqlite3.connect(f"file:{backup.resolve()}?mode=ro", uri=True) as source,
                sqlite3.connect(target) as destination,
            ):
                source.backup(destination)
                if destination.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError(f"invalid {name} backup")
                if name == "rounds":
                    applied = apply_migrations(destination)
                    result["databases"][name] = {
                        "status": "passed",
                        "applied_migrations": [m.version for m in applied],
                    }
        for name in ("knowledge", "fresh"):
            supervisor = CoreSupervisor(
                [
                    str(args.bundle.resolve() / "bin/ledgermind-core"),
                    "--database",
                    str(root / f"{name}.db"),
                ],
                core_data_dir=root,
                strict_isolation=False,
                semantic_language="en",
                resolution_pipeline="decision_v1",
                startup_timeout_seconds=60,
            )
            try:
                supervisor.start()
                handshake = supervisor.handshake_result
                assert handshake is not None
                if not handshake.get("capabilities", {}).get("resolution_decision"):
                    raise ValueError("Core decision capability is missing")
                result["databases"][name] = {
                    "status": "passed",
                    "knowledge_schema_version": handshake["knowledge_schema_version"],
                }
            finally:
                supervisor.close()
            with sqlite3.connect(root / f"{name}.db") as database:
                result["databases"][name]["sqlite_user_version"] = database.execute(
                    "PRAGMA user_version"
                ).fetchone()[0]
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
