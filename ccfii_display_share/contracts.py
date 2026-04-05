"""Shared capture backend contract types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class CaptureSourceDescriptor:
    """Normalized source information exposed by any capture backend."""

    kind: str
    label: str
    title: str | None = None
    details: str = ""


@dataclass(frozen=True)
class CaptureBackendCapabilities:
    """Feature flags and notes that describe what a backend can do."""

    display_capture: bool = False
    window_capture: bool = False
    preview_capture: bool = False
    start_capture: bool = False
    stop_capture: bool = False
    permissions_required: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class BackendError:
    """Normalized error payload returned by a backend."""

    code: str
    message: str
    details: str = ""
    recoverable: bool = True


@runtime_checkable
class CaptureBackendContract(Protocol):
    """Methods a platform backend must implement."""

    name: str

    def list_displays(self) -> Sequence[CaptureSourceDescriptor]:
        """Return available displays."""

    def list_windows(self) -> Sequence[CaptureSourceDescriptor]:
        """Return available windows."""

    def capture_preview(
        self,
        source: CaptureSourceDescriptor,
        output_path: str | Path,
    ) -> Path:
        """Capture a preview image for the selected source."""

    def start_capture(
        self,
        source: CaptureSourceDescriptor,
        fps: int,
        quality: int,
    ) -> object:
        """Start streaming frames from the selected source."""

    def stop_capture(self) -> None:
        """Stop the active capture session."""

    def get_capabilities(self) -> CaptureBackendCapabilities:
        """Report feature support and platform notes."""

    def get_error(self) -> BackendError | None:
        """Report the latest backend error, if any."""
