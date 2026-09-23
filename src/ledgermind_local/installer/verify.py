"""Cryptographic verification for release and bundle artifacts."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

from .errors import SignatureVerificationError
from .manifest import ArtifactRecord


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(chunk_size), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SignatureVerificationError(f"cannot hash artifact: {path}") from exc
    return digest.hexdigest()


def _decode_signature(value: bytes | str) -> bytes:
    raw = value if isinstance(value, bytes) else value.strip().encode("ascii")
    if len(raw) == 64:
        return raw
    text = raw.decode("ascii", errors="strict").strip()
    try:
        decoded = base64.b64decode(text, validate=True)
        if len(decoded) == 64:
            return decoded
    except (ValueError, UnicodeError):
        decoded = b""
    try:
        decoded = bytes.fromhex(text)
    except ValueError as exc:
        raise SignatureVerificationError(
            "signature is not raw, base64, or hex"
        ) from exc
    if len(decoded) != 64:
        raise SignatureVerificationError("Ed25519 signature must contain 64 bytes")
    return decoded


def _decode_public_key(value: bytes | str) -> bytes:
    raw = value if isinstance(value, bytes) else value.strip().encode("ascii")
    if len(raw) == 32:
        return raw
    text = raw.decode("ascii", errors="strict").strip()
    try:
        decoded = base64.b64decode(text, validate=True)
        if len(decoded) == 32:
            return decoded
    except (ValueError, UnicodeError):
        decoded = b""
    try:
        decoded = bytes.fromhex(text)
    except ValueError as exc:
        raise SignatureVerificationError(
            "public key is not raw, base64, or hex"
        ) from exc
    if len(decoded) != 32:
        raise SignatureVerificationError("Ed25519 public key must contain 32 bytes")
    return decoded


def public_key_from_environment() -> bytes | None:
    value = os.environ.get("LEDGERMIND_INSTALLER_PUBLIC_KEY", "").strip()
    return _decode_public_key(value) if value else None


def verify_ed25519(
    data: bytes, signature: bytes | str, public_key: bytes | str
) -> None:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        key = Ed25519PublicKey.from_public_bytes(_decode_public_key(public_key))
        key.verify(_decode_signature(signature), data)
    except (InvalidSignature, ValueError, TypeError, SignatureVerificationError) as exc:
        raise SignatureVerificationError(
            "Ed25519 signature verification failed"
        ) from exc


def verify_file(path: str | Path, record: ArtifactRecord) -> None:
    target = Path(path)
    try:
        size = target.stat().st_size
    except OSError as exc:
        raise SignatureVerificationError(f"artifact is missing: {target}") from exc
    if size != record.size:
        raise SignatureVerificationError(
            f"artifact size mismatch for {target}: {size} != {record.size}"
        )
    actual = sha256_file(target)
    if actual.lower() != record.sha256.lower():
        raise SignatureVerificationError(f"artifact SHA-256 mismatch for {target}")


def verify_artifact_signature(
    path: str | Path,
    record: ArtifactRecord,
    *,
    public_key: bytes | str | None = None,
) -> None:
    if not record.signature:
        raise SignatureVerificationError(f"artifact signature is missing for {path}")
    key = public_key or public_key_from_environment()
    if key is None:
        raise SignatureVerificationError(
            "no public key is available for artifact verification"
        )
    verify_ed25519(Path(path).read_bytes(), record.signature, key)


def verify_manifest_bytes(
    manifest_bytes: bytes,
    signature: bytes | str,
    *,
    public_key: bytes | str | None = None,
) -> None:
    key = public_key or public_key_from_environment()
    if key is None:
        raise SignatureVerificationError("no embedded or configured Ed25519 public key")
    verify_ed25519(manifest_bytes, signature, key)


def verify_bundle_tree(
    bundle_root: str | Path,
    *,
    public_key: bytes | str | None = None,
) -> dict[str, object]:
    """Verify bundle manifest signature and every listed file."""

    root = Path(bundle_root)
    manifest_path = root / "bundle-manifest.json"
    signature_path = root / "signatures" / "manifest.sig"
    public_path = root / "signatures" / "manifest.pub"
    if not manifest_path.is_file() or not signature_path.is_file():
        raise SignatureVerificationError("signed bundle manifest is missing")
    key = public_key
    if key is None and public_path.is_file():
        key = public_path.read_bytes()
    verify_manifest_bytes(
        manifest_path.read_bytes(), signature_path.read_bytes(), public_key=key
    )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = payload["artifacts"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SignatureVerificationError("bundle manifest is invalid") from exc
    if not isinstance(artifacts, dict):
        raise SignatureVerificationError("bundle manifest artifacts are invalid")
    checked = 0
    for relative, record in artifacts.items():
        if not isinstance(record, dict):
            raise SignatureVerificationError("bundle artifact record is invalid")
        path = root / str(relative)
        if not path.is_file():
            raise SignatureVerificationError(f"bundle artifact is missing: {relative}")
        size = record.get("size")
        digest = record.get("sha256")
        if (
            not isinstance(size, int)
            or not isinstance(digest, str)
            or size != path.stat().st_size
            or digest.lower() != sha256_file(path).lower()
        ):
            raise SignatureVerificationError(
                f"bundle artifact verification failed: {relative}"
            )
        checked += 1
    core = root / "bin" / "ledgermind-core"
    core_signature = root / "signatures" / "ledgermind-core.sig"
    core_public = root / "signatures" / "ledgermind-core.pub"
    if not core.is_file() or not core_signature.is_file() or not core_public.is_file():
        raise SignatureVerificationError("signed Core binary or key is missing")
    verify_ed25519(
        core.read_bytes(), core_signature.read_bytes(), core_public.read_bytes()
    )
    return {
        "status": "passed",
        "manifest": str(manifest_path),
        "artifacts_checked": checked,
        "core_signature": "passed",
    }


__all__ = [
    "public_key_from_environment",
    "sha256_file",
    "verify_artifact_signature",
    "verify_bundle_tree",
    "verify_ed25519",
    "verify_file",
    "verify_manifest_bytes",
]
