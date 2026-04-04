"""CCFII Display Share — Mirror a Windows display over LAN via MJPEG."""

import threading
import sys
import ctypes
import subprocess
import argparse
import socket
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"
STREAM_WAIT_TIMEOUT = 2.0
STREAM_IDLE_RETRIES = 3


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


def extract_frames(data: bytes) -> tuple[list[bytes], bytes]:
    """Extract complete JPEG frames from a byte buffer.

    Scans for SOI (0xFFD8) and EOI (0xFFD9) markers.
    Returns (list_of_complete_frames, remaining_bytes).
    """
    frames = []
    while True:
        soi_pos = data.find(JPEG_SOI)
        if soi_pos == -1:
            # Keep trailing 0xFF in case it's half of a SOI split across chunks
            if data and data[-1:] == b"\xff":
                return frames, data[-1:]
            return frames, b""
        eoi_pos = data.find(JPEG_EOI, soi_pos + 2)
        if eoi_pos == -1:
            return frames, data[soi_pos:]
        frame_end = eoi_pos + 2
        frames.append(data[soi_pos:frame_end])
        data = data[frame_end:]


class FrameBuffer:
    """Thread-safe container for the latest MJPEG frame.

    Uses a version counter so each client only gets new frames,
    avoiding stale-frame re-sends.
    """

    def __init__(self):
        self._frame = None
        self._version = 0
        self._condition = threading.Condition()
        self._viewer_count = 0
        self._viewer_lock = threading.Lock()

    def update(self, frame: bytes):
        with self._condition:
            self._frame = frame
            self._version += 1
            self._condition.notify_all()

    def wait_for_new_frame(self, last_version: int,
                           timeout: float = 1.0) -> tuple[bytes | None, int]:
        """Block until a frame newer than last_version is available.

        Returns (frame_bytes, new_version). frame_bytes is None on timeout.
        """
        with self._condition:
            self._condition.wait_for(
                lambda: self._version > last_version, timeout=timeout)
            if self._version > last_version:
                return self._frame, self._version
            return None, last_version

    def add_viewer(self):
        with self._viewer_lock:
            self._viewer_count += 1
            count = self._viewer_count
        print(f"[+] Viewer connected ({count} active)")

    def remove_viewer(self):
        with self._viewer_lock:
            self._viewer_count -= 1
            count = self._viewer_count
        print(f"[-] Viewer disconnected ({count} active)")

    @property
    def viewer_count(self) -> int:
        with self._viewer_lock:
            return self._viewer_count


VIEWER_HTML = b"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Display Share</title>
<style>
  * { margin: 0; padding: 0; }
  body { background: #000; overflow: hidden; }
  img { width: 100vw; height: 100vh; object-fit: contain; }
  .status {
    position: fixed;
    left: 16px;
    bottom: 16px;
    padding: 8px 12px;
    border-radius: 999px;
    background: rgba(0, 0, 0, 0.65);
    color: #fff;
    font: 14px/1.2 sans-serif;
  }
</style>
</head>
<body>
<img id="stream" alt="Live Display">
<div id="status" class="status">Connecting...</div>
<script>
  const img = document.getElementById("stream");
  const status = document.getElementById("status");
  let retryDelay = 1000;
  let reconnectTimer = null;

  function scheduleReconnect() {
    if (reconnectTimer !== null) {
      return;
    }
    status.textContent = "Disconnected. Reconnecting...";
    reconnectTimer = setTimeout(connectStream, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 5000);
  }

  function connectStream() {
    reconnectTimer = null;
    status.textContent = "Connecting...";
    img.src = "/stream?ts=" + Date.now();
  }

  img.onload = () => {
    retryDelay = 1000;
    status.textContent = "";
  };

  img.onerror = () => {
    img.removeAttribute("src");
    scheduleReconnect();
  };

  window.addEventListener("online", connectStream);
  connectStream();
</script>
</body>
</html>"""



class StreamHandler(BaseHTTPRequestHandler):
    frame_buffer: FrameBuffer  # set on class before server starts
    BOUNDARY = b"frame"

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/":
            self._serve_viewer()
        elif route == "/stream":
            self._serve_stream()
        else:
            self.send_error(404)

    def _serve_viewer(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(VIEWER_HTML)))
        self.end_headers()
        self.wfile.write(VIEWER_HTML)

    def _serve_stream(self):
        self.send_response(200)
        self.send_header("Content-Type",
                         "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.frame_buffer.add_viewer()
        last_version = 0
        idle_retries = 0
        try:
            while True:
                frame, last_version = self.frame_buffer.wait_for_new_frame(
                    last_version, timeout=STREAM_WAIT_TIMEOUT)
                if frame is None:
                    idle_retries += 1
                    if idle_retries >= STREAM_IDLE_RETRIES:
                        break
                    continue
                idle_retries = 0
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame)}\r\n".encode())
                self.wfile.write(b"\r\n")
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # viewer disconnected
        finally:
            self.frame_buffer.remove_viewer()

    def log_message(self, format, *args):
        pass  # silence per-request logs


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
    """Build the ordered list of selectable capture targets."""
    targets = [CaptureTarget.desktop(monitor) for monitor in monitors]
    targets.extend(windows)
    return targets


def choose_capture_target(targets):
    """Present capture targets in console and let user pick one."""
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
    """Backward-compatible wrapper for monitor-only selection."""
    return choose_capture_target([CaptureTarget.desktop(m) for m in monitors])


def start_ffmpeg(target: CaptureTarget, fps: int, quality: int) -> subprocess.Popen:
    """Launch FFmpeg to capture the selected source as MJPEG to stdout."""
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
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    return proc


def stop_ffmpeg(proc: subprocess.Popen | None):
    """Stop FFmpeg if it is still running."""
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
    """Return FFmpeg stderr output, if any."""
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
    """Read FFmpeg stdout, extract frames, push to buffer. Runs in thread."""
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


def start_shutdown_watcher(shutdown_event: threading.Event,
                           server: ThreadingHTTPServer) -> threading.Thread:
    """Start a thread that shuts the server down when FFmpeg exits."""
    def watch_shutdown():
        shutdown_event.wait()
        print("[!] Initiating shutdown due to FFmpeg exit...")
        server.shutdown()

    thread = threading.Thread(target=watch_shutdown, daemon=True)
    thread.start()
    return thread


def start_reader_thread(proc: subprocess.Popen, frame_buffer: FrameBuffer,
                        shutdown_event: threading.Event,
                        stop_event: threading.Event) -> threading.Thread:
    """Start a reader thread for one FFmpeg process."""
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
        """Start capturing the selected source."""
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
        """Stop the active capture process."""
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
        """Prompt for a new source and hot-swap FFmpeg capture."""
        monitor = choose_capture_target(self.monitors)
        self.stop_capture()
        self.start_capture(monitor)
        print("[*] Capture source switched. Viewers stay connected on the same URL.")


class BroadcastManager:
    """Programmatic lifecycle manager for display sharing."""

    def __init__(self, targets, port: int, fps: int, quality: int,
                 handler_class=StreamHandler,
                 controller_factory=CaptureController,
                 server_factory=ThreadingHTTPServer,
                 shutdown_watcher_fn=start_shutdown_watcher,
                 lan_ip_fn=None):
        self.targets = targets
        self.port = port
        self.fps = fps
        self.quality = quality
        self.handler_class = handler_class
        self.controller_factory = controller_factory
        self.server_factory = server_factory
        self.shutdown_watcher_fn = shutdown_watcher_fn
        self.lan_ip_fn = lan_ip_fn or get_lan_ip
        self.frame_buffer = FrameBuffer()
        self.shutdown_event = threading.Event()
        self.controller = controller_factory(
            monitors=targets,
            fps=fps,
            quality=quality,
            frame_buffer=self.frame_buffer,
            shutdown_event=self.shutdown_event,
        )
        self.server = None
        self._server_thread = None
        self._watcher_thread = None
        self._is_running = False
        self._lock = threading.Lock()

    def start(self, target: CaptureTarget):
        with self._lock:
            if self._is_running:
                return
            self.shutdown_event.clear()
            self.controller.start_capture(target)
            self.handler_class.frame_buffer = self.frame_buffer
            self.server = self.server_factory(("0.0.0.0", self.port),
                                              self.handler_class)
            self._watcher_thread = self.shutdown_watcher_fn(
                self.shutdown_event, self.server)
            self._server_thread = threading.Thread(
                target=self.server.serve_forever,
                daemon=True,
            )
            self._server_thread.start()
            self._is_running = True

    def stop(self):
        with self._lock:
            if not self._is_running:
                return
            self.shutdown_event.set()
            self.controller.stop_capture()
            if self.server is not None:
                self.server.shutdown()
            server_thread = self._server_thread
            self._server_thread = None
            self.server = None
            self._is_running = False
        if server_thread is not None and server_thread.is_alive():
            server_thread.join(timeout=5)

    def switch_target(self, target: CaptureTarget):
        if not self._is_running:
            self.start(target)
            return
        self.controller.stop_capture()
        self.controller.start_capture(target)

    def get_status(self) -> dict[str, object]:
        current_target = self.controller.current_monitor
        return {
            "is_running": self._is_running,
            "viewer_count": self.frame_buffer.viewer_count,
            "viewer_url": f"http://{self.lan_ip_fn()}:{self.port}",
            "target_label": current_target.label if current_target else "",
            "fps": self.fps,
            "quality": self.quality,
        }


def handle_runtime_command(command: str, controller: CaptureController,
                           shutdown_event: threading.Event) -> bool:
    """Handle a runtime terminal command. Returns True if recognized."""
    normalized = command.strip().lower()
    if normalized in {"d", "display", "screen"}:
        controller.switch_monitor()
        return True
    if normalized in {"q", "quit", "exit"}:
        print("[*] Shutting down...")
        shutdown_event.set()
        return True
    if normalized in {"h", "help", "?"}:
        print("Commands: d = switch display/window, q = quit, h = help")
        return True
    return False


def start_command_listener(controller: CaptureController,
                           shutdown_event: threading.Event) -> threading.Thread:
    """Listen for terminal commands while the server is running."""
    def command_loop():
        print("Commands: d = switch display/window, q = quit, h = help")
        while not shutdown_event.is_set():
            try:
                command = input("> ")
            except EOFError:
                return
            if not handle_runtime_command(command, controller, shutdown_event):
                print("Unknown command. Type 'h' for help.")

    thread = threading.Thread(target=command_loop, daemon=True)
    thread.start()
    return thread


def get_lan_ip() -> str:
    """Get this machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    parser = argparse.ArgumentParser(
        description="Share a display over the local network.")
    parser.add_argument("--port", type=int, default=8080,
                        help="HTTP server port (default: 8080)")
    parser.add_argument("--fps", type=int, default=30,
                        help="Capture framerate (default: 30)")
    parser.add_argument("--quality", type=int, default=5,
                        help="JPEG quality 1-31, lower=better (default: 5)")
    args = parser.parse_args()

    monitors = list_monitors()
    if not monitors:
        print("No displays found.")
        sys.exit(1)
    targets = build_capture_targets(monitors, list_windows())

    frame_buffer = FrameBuffer()
    shutdown_event = threading.Event()
    controller = CaptureController(
        monitors=targets,
        fps=args.fps,
        quality=args.quality,
        frame_buffer=frame_buffer,
        shutdown_event=shutdown_event,
    )

    monitor = choose_capture_target(targets)
    controller.start_capture(monitor)

    StreamHandler.frame_buffer = frame_buffer
    server = ThreadingHTTPServer(("0.0.0.0", args.port), StreamHandler)
    start_shutdown_watcher(shutdown_event, server)
    start_command_listener(controller, shutdown_event)

    lan_ip = get_lan_ip()
    print(f"Stream live at http://{lan_ip}:{args.port}")
    print("Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        shutdown_event.set()
        controller.stop_capture()
        server.shutdown()


if __name__ == "__main__":
    main()
