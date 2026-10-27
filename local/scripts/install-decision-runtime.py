#!/usr/bin/env python3
"""Install Kev without pip, using an explicitly trusted release signing key."""

import argparse
import json
from pathlib import Path

from ledgermind_local.installer.decision_runtime import install_decision_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "archive",
        "manifest",
        "signature",
        "trusted-public-key",
        "destination",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    destination = install_decision_runtime(
        archive=args.archive,
        manifest=args.manifest,
        signature=args.signature,
        trusted_public_key=args.trusted_public_key.read_bytes(),
        destination=args.destination,
    )
    print(json.dumps({"status": "installed", "runtime_path": str(destination)}))


if __name__ == "__main__":
    main()
