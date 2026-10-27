from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class CoreBinaryVerificationError(RuntimeError):
    """Core binary signature or artifact validation failed."""


@dataclass(frozen=True, slots=True)
class CoreBinaryVerification:
    binary_path: Path
    sha256: str
    signature_path: Path
    public_key_path: Path
    signature_verified: bool = True


def verify_core_binary(
    binary_path: str | Path,
    *,
    signature_path: str | Path,
    public_key_path: str | Path,
) -> CoreBinaryVerification:
    """Verify an Ed25519 signature over the complete Core binary."""

    binary = Path(binary_path).expanduser()
    signature = Path(signature_path).expanduser()
    public_key = Path(public_key_path).expanduser()
    if not binary.is_file():
        raise CoreBinaryVerificationError(f"Core binary not found: {binary}")
    if not signature.is_file():
        raise CoreBinaryVerificationError(f"Core signature not found: {signature}")
    if not public_key.is_file():
        raise CoreBinaryVerificationError(f"Core public key not found: {public_key}")

    try:
        binary_bytes = binary.read_bytes()
        signature_bytes = _decode_artifact(signature, expected_size=64, label="signature")
        public_key_bytes = _decode_artifact(
            public_key,
            expected_size=32,
            label="public key",
        )
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes,
            binary_bytes,
        )
    except CoreBinaryVerificationError:
        raise
    except (InvalidSignature, OSError, ValueError, binascii.Error) as exc:
        raise CoreBinaryVerificationError(
            f"Core binary verification failed for {binary}"
        ) from exc

    return CoreBinaryVerification(
        binary_path=binary,
        sha256=hashlib.sha256(binary_bytes).hexdigest(),
        signature_path=signature,
        public_key_path=public_key,
    )


def calculate_sha256(path: str | Path) -> str:
    """Return the SHA-256 digest for a local artifact."""

    digest = hashlib.sha256()
    with Path(path).expanduser().open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_artifact(path: Path, *, expected_size: int, label: str) -> bytes:
    raw = path.read_bytes()
    if len(raw) == expected_size:
        return raw

    try:
        text = raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise CoreBinaryVerificationError(f"invalid Core {label} encoding") from exc

    if len(text) == expected_size * 2:
        try:
            decoded = bytes.fromhex(text)
        except ValueError as exc:
            raise CoreBinaryVerificationError(f"invalid Core {label} hex") from exc
        if len(decoded) == expected_size:
            return decoded

    try:
        decoded = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise CoreBinaryVerificationError(f"invalid Core {label} base64") from exc
    if len(decoded) != expected_size:
        raise CoreBinaryVerificationError(f"invalid Core {label} size")
    return decoded


__all__ = [
    "CoreBinaryVerification",
    "CoreBinaryVerificationError",
    "calculate_sha256",
    "verify_core_binary",
]
