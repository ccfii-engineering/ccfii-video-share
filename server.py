"""Compatibility exports for legacy imports and CLI usage."""

from ccfii_display_share import (
    APP_COLORS,
    APP_NAME,
    BackendError,
    BroadcastManager,
    CaptureBackendCapabilities,
    CaptureBackendContract,
    CaptureSourceDescriptor,
    CaptureController,
    CaptureTarget,
    FrameBuffer,
    STREAM_IDLE_RETRIES,
    STREAM_WAIT_TIMEOUT,
    StreamHandler,
    VIEWER_HTML,
    build_capture_targets,
    build_preview_command,
    capture_preview_image,
    choose_capture_target,
    choose_monitor,
    extract_frames,
    ffmpeg_reader,
    get_lan_ip,
    handle_runtime_command,
    list_monitors,
    list_windows,
    read_ffmpeg_stderr,
    resolve_ffmpeg_command,
    start_command_listener,
    start_ffmpeg,
    start_reader_thread,
    start_shutdown_watcher,
    stop_ffmpeg,
)
from ccfii_display_share.cli import main as cli_main
import subprocess


def main():
    """Run the legacy CLI entrypoint."""
    cli_main()


if __name__ == "__main__":
    main()
