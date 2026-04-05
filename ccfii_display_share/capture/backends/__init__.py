"""Platform capture backend registry."""

from __future__ import annotations

import sys

from .macos import MacOSCaptureBackend
from .windows import WindowsCaptureBackend


def get_backend(platform_name: str | None = None):
    resolved_platform = platform_name or sys.platform
    if resolved_platform == "darwin":
        return MacOSCaptureBackend()
    return WindowsCaptureBackend()


__all__ = ["MacOSCaptureBackend", "WindowsCaptureBackend", "get_backend"]
