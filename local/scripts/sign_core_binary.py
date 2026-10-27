"""Sign an exact LedgerMind Core binary for Local gateway verification."""

from __future__ import annotations

import argparse
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _private_key(path: Path) -> Ed25519PrivateKey:
    payload = path.read_bytes()
    if len(payload) == 32:
        return Ed25519PrivateKey.from_private_bytes(payload)

    loaded = serialization.load_pem_private_key(payload, password=None)
    if not isinstance(loaded, Ed25519PrivateKey):
        raise TypeError(f"{path} does not contain an Ed25519 private key")
    return loaded


def _output_path(value: str | None, binary: Path, suffix: str) -> Path:
    return Path(value) if value else binary.with_suffix(suffix)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sign a Rust Core binary with an Ed25519 private key"
    )
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--signature", type=Path)
    parser.add_argument("--public-key", type=Path)
    args = parser.parse_args()

    binary = args.binary
    if not binary.is_file():
        parser.error(f"Core binary does not exist: {binary}")

    private_key = _private_key(args.private_key)
    signature_path = _output_path(args.signature, binary, ".sig")
    public_key_path = _output_path(args.public_key, binary, ".pub")
    signature_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    public_key_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    signature_path.write_bytes(private_key.sign(binary.read_bytes()))
    public_key_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    )
    signature_path.chmod(0o644)
    public_key_path.chmod(0o644)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
