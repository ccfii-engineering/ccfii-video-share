"""Public package exports for CCFII Display Share."""

from .capture import (
    CaptureController,
    CaptureTarget,
    build_capture_targets,
    build_preview_command,
    capture_preview_image,
    choose_capture_target,
    choose_monitor,
    ffmpeg_reader,
    list_monitors,
    list_windows,
    read_ffmpeg_stderr,
    resolve_ffmpeg_command,
    start_ffmpeg,
    start_reader_thread,
    stop_ffmpeg,
)
from .config import APP_COLORS, APP_NAME, STREAM_IDLE_RETRIES, STREAM_WAIT_TIMEOUT
from .manager import (
    BroadcastManager,
    get_lan_ip,
    handle_runtime_command,
    start_command_listener,
    start_shutdown_watcher,
)
from .streaming import FrameBuffer, StreamHandler, VIEWER_HTML, extract_frames

__all__ = [
    "APP_COLORS",
    "APP_NAME",
    "BroadcastManager",
    "CaptureController",
    "CaptureTarget",
    "FrameBuffer",
    "STREAM_IDLE_RETRIES",
    "STREAM_WAIT_TIMEOUT",
    "StreamHandler",
    "VIEWER_HTML",
    "build_capture_targets",
    "build_preview_command",
    "capture_preview_image",
    "choose_capture_target",
    "choose_monitor",
    "extract_frames",
    "ffmpeg_reader",
    "get_lan_ip",
    "handle_runtime_command",
    "list_monitors",
    "list_windows",
    "read_ffmpeg_stderr",
    "resolve_ffmpeg_command",
    "start_command_listener",
    "start_ffmpeg",
    "start_reader_thread",
    "start_shutdown_watcher",
    "stop_ffmpeg",
]
