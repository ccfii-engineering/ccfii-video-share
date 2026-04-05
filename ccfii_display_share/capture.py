"""Display/window discovery and FFmpeg capture lifecycle."""

from __future__ import annotations

import ctypes
from io import BytesIO
from pathlib import Path
from functools import lru_cache
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass

try:
    from PIL import Image, ImageGrab
except ModuleNotFoundError:  # pragma: no cover - depends on local Python build
    Image = None
    ImageGrab = None

try:
    import mss
except ModuleNotFoundError:  # pragma: no cover - depends on local Python build
    mss = None

from .streaming import FrameBuffer, extract_frames


__path__ = [str(Path(__file__).resolve().with_name("capture"))]


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


def _list_monitors_system():
    """Return list of monitors with physical pixel coordinates."""
    if sys.platform == "win32":
        ctypes.windll.user32.SetProcessDPIAware()
    from screeninfo import get_monitors
    return get_monitors()


def _list_windows_system():
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


@lru_cache(maxsize=1)
def resolve_capture_backend():
    from .capture.backends import get_backend

    return get_backend()


def list_monitors():
    backend = resolve_capture_backend()
    return backend.list_displays()


def list_windows():
    backend = resolve_capture_backend()
    return backend.list_windows()


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


def resolve_ffmpeg_command(
    packaged_path: str | Path | None = None,
    path_lookup=shutil.which,
) -> str:
    """Resolve the ffmpeg executable from bundled or system locations."""
    candidates: list[Path] = []
    if packaged_path is not None:
        candidates.append(Path(packaged_path))

    executable_dir = Path(sys.executable).resolve().parent
    module_root = Path(__file__).resolve().parents[1]
    candidates.extend([
        executable_dir / "ffmpeg.exe",
        executable_dir / "bundled-bin" / "ffmpeg.exe",
        module_root / "bundled-bin" / "ffmpeg.exe",
    ])

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.extend([
            Path(meipass) / "ffmpeg.exe",
            Path(meipass) / "bundled-bin" / "ffmpeg.exe",
        ])

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    system_ffmpeg = path_lookup("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    return "ffmpeg"


def build_subprocess_window_kwargs() -> dict[str, object]:
    """Hide FFmpeg console windows when running as a GUI app on Windows."""
    if sys.platform != "win32":
        return {}

    kwargs: dict[str, object] = {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    kwargs["startupinfo"] = startupinfo
    return kwargs


def start_ffmpeg(target: CaptureTarget, fps: int, quality: int) -> subprocess.Popen:
    cmd = [
        resolve_ffmpeg_command(),
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
        **build_subprocess_window_kwargs(),
    )


def build_preview_command(target: CaptureTarget, output_path: str | Path) -> list[str]:
    """Build a one-frame FFmpeg command for source preview snapshots."""
    cmd = [
        resolve_ffmpeg_command(),
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


def map_quality_to_jpeg_quality(quality: int) -> int:
    """Convert FFmpeg-style qscale values to Pillow JPEG quality."""
    return max(35, min(95, 100 - (quality * 2)))


def capture_desktop_preview_image(target: CaptureTarget, output_path: str | Path) -> Path:
    """Capture a display preview without FFmpeg for better Windows reliability."""
    if ImageGrab is None:
        raise RuntimeError("Pillow ImageGrab is not available in this Python environment.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    bbox = (
        int(target.x or 0),
        int(target.y or 0),
        int((target.x or 0) + (target.width or 0)),
        int((target.y or 0) + (target.height or 0)),
    )
    image = ImageGrab.grab(bbox=bbox, all_screens=True)
    image.save(output)
    return output


def capture_preview_image(target: CaptureTarget, output_path: str | Path) -> Path:
    """Capture a preview snapshot for the selected source."""
    if target.kind == "desktop":
        return capture_desktop_preview_image(target, output_path)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        build_preview_command(target, output),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        **build_subprocess_window_kwargs(),
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


def encode_screenshot_frame(target: CaptureTarget, quality: int) -> bytes:
    """Encode a desktop screenshot to JPEG bytes for the MJPEG stream."""
    if mss is None or Image is None:
        raise RuntimeError("Desktop capture dependencies are not available.")

    monitor = {
        "left": int(target.x or 0),
        "top": int(target.y or 0),
        "width": int(target.width or 0),
        "height": int(target.height or 0),
    }

    with mss.mss() as sct:
        shot = sct.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=map_quality_to_jpeg_quality(quality))
        return buffer.getvalue()


def desktop_capture_reader(
    target: CaptureTarget,
    fps: int,
    quality: int,
    buffer: FrameBuffer,
    shutdown_event: threading.Event,
    stop_event: threading.Event,
):
    frame_interval = 1.0 / max(1, fps)
    last_error = ""
    while not shutdown_event.is_set() and not stop_event.is_set():
        started_at = time.perf_counter()
        try:
            frame = encode_screenshot_frame(target, quality)
            buffer.update(frame)
        except Exception as exc:
            last_error = str(exc).strip()
            break
        elapsed = time.perf_counter() - started_at
        remaining = frame_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)

    if not stop_event.is_set() and last_error:
        setattr(shutdown_event, "ffmpeg_error", last_error)
        shutdown_event.set()


def start_desktop_reader_thread(target: CaptureTarget,
                                fps: int,
                                quality: int,
                                frame_buffer: FrameBuffer,
                                shutdown_event: threading.Event,
                                stop_event: threading.Event) -> threading.Thread:
    thread = threading.Thread(
        target=desktop_capture_reader,
        args=(target, fps, quality, frame_buffer, shutdown_event, stop_event),
        daemon=True,
    )
    thread.start()
    return thread


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
    setattr(shutdown_event, "ffmpeg_error", stderr_details)
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
        setattr(self.shutdown_event, "ffmpeg_error", "")
        stop_event = threading.Event()
        if monitor.kind == "desktop":
            proc = None
            reader_thread = start_desktop_reader_thread(
                monitor,
                self.fps,
                self.quality,
                self.frame_buffer,
                self.shutdown_event,
                stop_event,
            )
        else:
            proc = self._start_ffmpeg(monitor, self.fps, self.quality)
            time.sleep(0.2)
            if hasattr(proc, "poll") and proc.poll() is not None:
                stderr_details = read_ffmpeg_stderr(proc) or "FFmpeg exited before capture started."
                raise RuntimeError(stderr_details)
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
