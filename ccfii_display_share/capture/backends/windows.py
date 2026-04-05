"""Windows capture backend adapter."""

from __future__ import annotations

from pathlib import Path

from ...contracts import CaptureBackendCapabilities
from .. import (
    _list_monitors_system,
    _list_windows_system,
    capture_preview_image,
    start_ffmpeg,
    stop_ffmpeg,
)


class WindowsCaptureBackend:
    name = "windows"

    def __init__(self):
        self._proc = None

    def list_displays(self):
        return _list_monitors_system()

    def list_windows(self):
        return _list_windows_system()

    def capture_preview(self, source, output_path: str | Path):
        return capture_preview_image(source, output_path)

    def start_capture(self, source, fps: int, quality: int):
        self._proc = start_ffmpeg(source, fps, quality)
        return self._proc

    def stop_capture(self):
        stop_ffmpeg(self._proc)
        self._proc = None

    def get_capabilities(self):
        return CaptureBackendCapabilities(
            display_capture=True,
            window_capture=True,
            preview_capture=True,
            start_capture=True,
            stop_capture=True,
            notes=("Windows gdigrab backend",),
        )

    def get_error(self):
        return None
