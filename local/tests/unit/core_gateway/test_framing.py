from __future__ import annotations

from io import BytesIO

import pytest

from ledgermind_local.core_gateway.framing import (
    MAX_FRAME_BYTES,
    FrameTooLargeError,
    read_frame,
    write_frame,
)


class _FragmentedReader:
    def __init__(self, payload: bytes, chunk_size: int) -> None:
        self._payload = payload
        self._chunk_size = chunk_size

    def read(self, size: int = -1) -> bytes:
        del size
        if not self._payload:
            return b""
        chunk, self._payload = (
            self._payload[: self._chunk_size],
            self._payload[self._chunk_size :],
        )
        return chunk


def test_read_frame_handles_fragmented_prefix_and_payload() -> None:
    stream = _FragmentedReader(b"\x00\x00\x00\x05hello", chunk_size=1)

    assert read_frame(stream) == b"hello"


def test_write_and_read_frame_support_back_to_back_messages() -> None:
    stream = BytesIO()
    write_frame(stream, b"one")
    write_frame(stream, b"two")
    stream.seek(0)

    assert read_frame(stream) == b"one"
    assert read_frame(stream) == b"two"


def test_read_frame_rejects_oversized_payload_before_reading_body() -> None:
    stream = BytesIO((MAX_FRAME_BYTES + 1).to_bytes(4, "big"))

    with pytest.raises(FrameTooLargeError):
        read_frame(stream)

    assert stream.tell() == 4
