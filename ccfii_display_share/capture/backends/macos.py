"""macOS capture backend for display preview with permission-aware errors."""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import ImageGrab
except ModuleNotFoundError:  # pragma: no cover - depends on local Python build
    ImageGrab = None

from ...contracts import BackendError, CaptureBackendCapabilities
from .. import CaptureTarget

try:
    from screeninfo import get_monitors
except ModuleNotFoundError:  # pragma: no cover - depends on local Python build
    get_monitors = None


def list_monitors():
    if get_monitors is None:
        return []
    return get_monitors()


def _is_permission_denied(error: Exception) -> bool:
    message = str(error).lower()
    return any(token in message for token in ("not authorized", "permission", "denied"))


class MacOSCaptureBackend:
    name = "macos"

    def __init__(self):
        self._error: BackendError | None = None

    def list_displays(self):
        return [CaptureTarget.desktop(monitor) for monitor in list_monitors()]

    def list_windows(self):
        return []

    def capture_preview(self, source, output_path: str | Path):
        if ImageGrab is None:
            self._error = BackendError(
                code="macos_preview_unavailable",
                message="Pillow ImageGrab is not available in this Python environment.",
                details="Install Pillow to enable macOS display preview capture.",
                recoverable=True,
            )
            raise RuntimeError(self._error.message)
        try:
            self._error = None
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            bbox = (
                int(getattr(source, "x", 0) or 0),
                int(getattr(source, "y", 0) or 0),
                int((getattr(source, "x", 0) or 0) + (getattr(source, "width", 0) or 0)),
                int((getattr(source, "y", 0) or 0) + (getattr(source, "height", 0) or 0)),
            )
            image = ImageGrab.grab(bbox=bbox, all_screens=True)
            image.save(output)
            return output
        except Exception as exc:
            if _is_permission_denied(exc):
                self._error = BackendError(
                    code="macos_screen_recording_permission_denied",
                    message="Screen Recording permission is required for macOS display preview.",
                    details=(
                        "Open System Settings, grant Screen Recording permission to CCFII Display Share, "
                        "then refresh the preview."
                    ),
                    recoverable=True,
                )
            else:
                self._error = BackendError(
                    code="macos_preview_failed",
                    message="macOS display preview failed.",
                    details=str(exc),
                    recoverable=True,
                )
            raise RuntimeError(self._error.message) from exc

    def start_capture(self, source, fps: int, quality: int):
        self._error = BackendError(
            code="macos_capture_not_implemented",
            message="macOS live display broadcasting is not implemented yet.",
            details="Preview capture works, but live broadcast capture for macOS still needs platform-specific frame streaming.",
            recoverable=True,
        )
        raise RuntimeError(self._error.message)

    def stop_capture(self):
        return None

    def get_capabilities(self):
        return CaptureBackendCapabilities(
            display_capture=False,
            window_capture=False,
            preview_capture=True,
            start_capture=False,
            stop_capture=True,
            permissions_required=("Screen Recording",),
            notes=(
                "macOS preview capture available",
                "Live display broadcasting for macOS is not implemented yet.",
                "Grant Screen Recording permission in System Settings if preview fails.",
            ),
        )

    def get_error(self):
        return self._error
