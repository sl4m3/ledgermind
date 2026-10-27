"""Conservative CPU/GPU detection for signed embedding assets."""

from __future__ import annotations

import os
import platform
import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Device:
    kind: str
    available: bool
    name: str
    memory_bytes: int | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "available": self.available,
            "name": self.name,
            "memory_bytes": self.memory_bytes,
            "detail": self.detail,
        }


def _command_output(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def detect_devices() -> tuple[Device, ...]:
    ram_bytes = _ram_bytes()
    devices = [
        Device(
            "cpu",
            True,
            platform.processor() or platform.machine(),
            memory_bytes=ram_bytes,
            detail=f"{os.cpu_count() or 1} threads",
        )
    ]
    nvidia = _command_output(
        ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"]
    )
    if nvidia:
        first = nvidia.splitlines()[0]
        name, _, memory = first.partition(",")
        number = re.search(r"[0-9]+", memory)
        devices.append(
            Device(
                "cuda",
                True,
                name.strip() or "NVIDIA GPU",
                int(number.group()) * 1024 * 1024 if number else None,
            )
        )
    rocm = _command_output(["rocminfo"])
    if rocm or os.path.exists("/dev/kfd"):
        devices.append(
            Device(
                "rocm", True, "AMD ROCm device", detail="rocminfo or /dev/kfd detected"
            )
        )
    return tuple(devices)


def _ram_bytes() -> int | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def choose_device(requested: str, *, supported: set[str] | None = None) -> Device:
    devices = {device.kind: device for device in detect_devices()}
    supported = supported or set(devices)
    if requested == "auto":
        for kind in ("cuda", "rocm", "cpu"):
            if (
                kind in supported
                and devices.get(kind, Device(kind, False, kind)).available
            ):
                return devices[kind]
        raise RuntimeError("no supported embedding device is available")
    device = devices.get(requested)
    if requested not in supported or device is None or not device.available:
        raise RuntimeError(f"requested embedding device is unavailable: {requested}")
    return device


__all__ = ["Device", "choose_device", "detect_devices"]
