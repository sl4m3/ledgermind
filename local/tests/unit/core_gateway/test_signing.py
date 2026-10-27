from __future__ import annotations

import base64
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ledgermind_local.core_gateway.signing import (
    CoreBinaryVerificationError,
    verify_core_binary,
)


def test_verify_core_binary_returns_sha256_and_accepts_base64_artifacts(
    tmp_path: Path,
) -> None:
    binary_path = tmp_path / "ledgermind-core"
    signature_path = tmp_path / "ledgermind-core.sig"
    public_key_path = tmp_path / "ledgermind-core.pub"
    binary = b"signed Core release bytes\n"
    binary_path.write_bytes(binary)

    private_key = Ed25519PrivateKey.generate()
    signature_path.write_text(
        base64.b64encode(private_key.sign(binary)).decode("ascii"),
        encoding="ascii",
    )
    public_key_path.write_text(
        base64.b64encode(
            private_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).decode("ascii"),
        encoding="ascii",
    )

    result = verify_core_binary(
        binary_path,
        signature_path=signature_path,
        public_key_path=public_key_path,
    )

    assert result.signature_verified is True
    assert result.sha256 == "bfeaf2423d027e0ea433898a92e22dfb509d8df44758f01527f3f713c1ee1dad"


def test_verify_core_binary_rejects_tampering(tmp_path: Path) -> None:
    binary_path = tmp_path / "ledgermind-core"
    signature_path = tmp_path / "ledgermind-core.sig"
    public_key_path = tmp_path / "ledgermind-core.pub"
    binary_path.write_bytes(b"original bytes")

    private_key = Ed25519PrivateKey.generate()
    signature_path.write_bytes(private_key.sign(binary_path.read_bytes()))
    public_key_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    )
    binary_path.write_bytes(b"tampered bytes")

    with pytest.raises(CoreBinaryVerificationError, match="verification failed"):
        verify_core_binary(
            binary_path,
            signature_path=signature_path,
            public_key_path=public_key_path,
        )
