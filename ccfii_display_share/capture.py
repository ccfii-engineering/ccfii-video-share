"""Display/window discovery and FFmpeg capture lifecycle."""

from __future__ import annotations

import ctypes
from pathlib import Path
import subprocess
import sys
import threading
from dataclasses import dataclass

from .streaming import FrameBuffer, extract_frames


@dataclass(frozen=True)
class CaptureTarget:
    """A selectable FFmpeg capture source."""

    kind: str
    label: str
    input_name: str
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    hwnd: int | None = None
    title: str | None = None

    @classmethod
    def desktop(cls, monitor):
        label = (f"Desktop: {monitor.name or 'Display'} - "
                 f"{monitor.width}x{monitor.height} at ({monitor.x}, {monitor.y})")
        return cls(
            kind="desktop",
            label=label,
            input_name="desktop",
            x=monitor.x,
            y=monitor.y,
            width=monitor.width,
            height=monitor.height,
        )

    @classmethod
    def window(cls, hwnd: int, title: str):
        return cls(
            kind="window",
            label=f"Window: {title}",
            input_name=f"title={title}",
            hwnd=hwnd,
            title=title,
        )


def list_monitors():
    """Return list of monitors with physical pixel coordinates."""
    if sys.platform == "win32":
        ctypes.windll.user32.SetProcessDPIAware()
    from screeninfo import get_monitors
    return get_monitors()


def list_windows():
    """Return visible top-level windows that have titles."""
    if sys.platform != "win32":
        return []

    user32 = ctypes.windll.user32
    windows = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                         ctypes.c_void_p)

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        title = title_buffer.value.strip()
        if not title:
            return True
        windows.append(CaptureTarget.window(int(hwnd), title))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    windows.sort(key=lambda item: item.label.lower())
    return windows


def build_capture_targets(monitors, windows):
    targets = [CaptureTarget.desktop(monitor) for monitor in monitors]
    targets.extend(windows)
    return targets


def choose_capture_target(targets):
    print("\nAvailable capture sources:\n")
    for i, target in enumerate(targets):
        print(f"  [{i + 1}] {target.label}")
    print()
    while True:
        try:
            choice = int(input(f"Select source (1-{len(targets)}): "))
            if 1 <= choice <= len(targets):
                return targets[choice - 1]
        except (ValueError, EOFError):
            pass
        print("Invalid choice, try again.")


def choose_monitor(monitors):
    return choose_capture_target([CaptureTarget.desktop(m) for m in monitors])


def start_ffmpeg(target: CaptureTarget, fps: int, quality: int) -> subprocess.Popen:
    cmd = [
        "ffmpeg",
        "-f", "gdigrab",
        "-framerate", str(fps),
    ]
    if target.kind == "desktop":
        cmd.extend([
            "-offset_x", str(target.x),
            "-offset_y", str(target.y),
            "-video_size", f"{target.width}x{target.height}",
        ])
    cmd.extend([
        "-i", target.input_name,
        "-f", "mjpeg",
        "-q:v", str(quality),
        "-an",
        "-"
    ])
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )


def build_preview_command(target: CaptureTarget, output_path: str | Path) -> list[str]:
    """Build a one-frame FFmpeg command for source preview snapshots."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "gdigrab",
        "-framerate", "5",
    ]
    if target.kind == "desktop":
        cmd.extend([
            "-offset_x", str(target.x),
            "-offset_y", str(target.y),
            "-video_size", f"{target.width}x{target.height}",
        ])
    cmd.extend([
        "-i", target.input_name,
        "-frames:v", "1",
        "-update", "1",
        str(output_path),
    ])
    return cmd


def capture_preview_image(target: CaptureTarget, output_path: str | Path) -> Path:
    """Capture a preview snapshot for the selected source."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        build_preview_command(target, output),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    return output


def stop_ffmpeg(proc: subprocess.Popen | None):
    if proc is None:
        return
    try:
        proc.terminate()
    except Exception:
        return
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def read_ffmpeg_stderr(proc: subprocess.Popen) -> str:
    if proc.stderr is None:
        return ""
    try:
        stderr_output = proc.stderr.read()
    except Exception:
        return ""
    if not stderr_output:
        return ""
    if isinstance(stderr_output, bytes):
        return stderr_output.decode("utf-8", errors="replace").strip()
    return str(stderr_output).strip()


def ffmpeg_reader(proc: subprocess.Popen, buffer: FrameBuffer,
                  shutdown_event: threading.Event,
                  stop_event: threading.Event | None = None):
    leftover = b""
    while True:
        chunk = proc.stdout.read(65536)
        if not chunk:
            break
        leftover += chunk
        frames, leftover = extract_frames(leftover)
        for frame in frames:
            buffer.update(frame)
    if stop_event is not None and stop_event.is_set():
        return
    stderr_details = read_ffmpeg_stderr(proc)
    print("\n[!] FFmpeg process exited unexpectedly.")
    if stderr_details:
        print(stderr_details)
    shutdown_event.set()


def start_reader_thread(proc: subprocess.Popen, frame_buffer: FrameBuffer,
                        shutdown_event: threading.Event,
                        stop_event: threading.Event) -> threading.Thread:
    thread = threading.Thread(
        target=ffmpeg_reader,
        args=(proc, frame_buffer, shutdown_event, stop_event),
        daemon=True,
    )
    thread.start()
    return thread


class CaptureController:
    """Manage FFmpeg capture lifecycle while the HTTP server stays up."""

    def __init__(self, monitors, fps: int, quality: int,
                 frame_buffer: FrameBuffer,
                 shutdown_event: threading.Event,
                 start_ffmpeg_fn=start_ffmpeg,
                 stop_ffmpeg_fn=stop_ffmpeg,
                 start_reader_fn=start_reader_thread):
        self.monitors = monitors
        self.fps = fps
        self.quality = quality
        self.frame_buffer = frame_buffer
        self.shutdown_event = shutdown_event
        self._start_ffmpeg = start_ffmpeg_fn
        self._stop_ffmpeg = stop_ffmpeg_fn
        self._start_reader = start_reader_fn
        self._proc = None
        self._reader_thread = None
        self._stop_event = None
        self._monitor = None
        self._lock = threading.Lock()

    @property
    def current_monitor(self):
        return self._monitor

    def start_capture(self, monitor):
        proc = self._start_ffmpeg(monitor, self.fps, self.quality)
        stop_event = threading.Event()
        reader_thread = self._start_reader(
            proc, self.frame_buffer, self.shutdown_event, stop_event)
        with self._lock:
            self._proc = proc
            self._reader_thread = reader_thread
            self._stop_event = stop_event
            self._monitor = monitor
        print(f"\nCapturing: {monitor.label} @ {self.fps}fps\n")
        return proc

    def stop_capture(self):
        with self._lock:
            proc = self._proc
            reader_thread = self._reader_thread
            stop_event = self._stop_event
            self._proc = None
            self._reader_thread = None
            self._stop_event = None
        if stop_event is not None:
            stop_event.set()
        self._stop_ffmpeg(proc)
        if reader_thread is not None and reader_thread.is_alive():
            reader_thread.join(timeout=5)

    def switch_monitor(self):
        monitor = choose_capture_target(self.monitors)
        self.stop_capture()
        self.start_capture(monitor)
        print("[*] Capture source switched. Viewers stay connected on the same URL.")
