"""Length-prefixed Core IPC framing."""

from __future__ import annotations

from typing import Protocol

MAX_FRAME_BYTES = 8 * 1024 * 1024
_FRAME_HEADER_BYTES = 4


class FrameError(ValueError):
    """Base error for malformed or truncated IPC frames."""


class FrameTooLargeError(FrameError):
    """The declared frame length exceeds the protocol limit."""


class FrameTruncatedError(FrameError):
    """The stream ended before a complete frame was received."""


class _Readable(Protocol):
    def read(self, size: int = -1) -> bytes: ...


class _Writable(Protocol):
    def write(self, data: bytes) -> object: ...

    def flush(self) -> object: ...


def _read_exact(reader: _Readable, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = reader.read(remaining)
        if not chunk:
            raise FrameTruncatedError(
                f"stream ended with {remaining} frame bytes still required"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(reader: _Readable) -> bytes:
    """Read one length-prefixed payload from a binary stream."""
    header = _read_exact(reader, _FRAME_HEADER_BYTES)
    length = int.from_bytes(header, byteorder="big", signed=False)
    if length > MAX_FRAME_BYTES:
        raise FrameTooLargeError(
            f"frame length {length} exceeds {MAX_FRAME_BYTES} byte limit"
        )
    return _read_exact(reader, length)


def write_frame(writer: _Writable, payload: bytes) -> None:
    """Write and flush one length-prefixed payload to a binary stream."""
    length = len(payload)
    if length > MAX_FRAME_BYTES:
        raise FrameTooLargeError(
            f"frame length {length} exceeds {MAX_FRAME_BYTES} byte limit"
        )
    writer.write(length.to_bytes(_FRAME_HEADER_BYTES, byteorder="big") + payload)
    writer.flush()


__all__ = [
    "MAX_FRAME_BYTES",
    "FrameError",
    "FrameTooLargeError",
    "FrameTruncatedError",
    "read_frame",
    "write_frame",
]
