"""CCFII Display Share — Mirror a Windows display over LAN via MJPEG."""

import threading
import sys
import ctypes
import subprocess
import argparse
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


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
</style>
</head>
<body>
<img src="/stream" alt="Live Display">
</body>
</html>"""



class StreamHandler(BaseHTTPRequestHandler):
    frame_buffer: FrameBuffer  # set on class before server starts
    BOUNDARY = b"frame"

    def do_GET(self):
        if self.path == "/":
            self._serve_viewer()
        elif self.path == "/stream":
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
        try:
            while True:
                frame, last_version = self.frame_buffer.wait_for_new_frame(
                    last_version, timeout=2.0)
                if frame is None:
                    continue
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame)}\r\n".encode())
                self.wfile.write(b"\r\n")
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")
        except (BrokenPipeError, ConnectionResetError):
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


def choose_monitor(monitors):
    """Present monitors in console and let user pick one."""
    print("\nAvailable displays:\n")
    for i, m in enumerate(monitors):
        print(f"  [{i + 1}] {m.name or 'Display'} — "
              f"{m.width}x{m.height} at ({m.x}, {m.y})")
    print()
    while True:
        try:
            choice = int(input(f"Select display (1-{len(monitors)}): "))
            if 1 <= choice <= len(monitors):
                return monitors[choice - 1]
        except (ValueError, EOFError):
            pass
        print("Invalid choice, try again.")


def start_ffmpeg(monitor, fps: int, quality: int) -> subprocess.Popen:
    """Launch FFmpeg to capture the given monitor as MJPEG to stdout."""
    cmd = [
        "ffmpeg",
        "-f", "gdigrab",
        "-framerate", str(fps),
        "-offset_x", str(monitor.x),
        "-offset_y", str(monitor.y),
        "-video_size", f"{monitor.width}x{monitor.height}",
        "-i", "desktop",
        "-f", "mjpeg",
        "-q:v", str(quality),
        "-an",
        "-"
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )
    return proc


def ffmpeg_reader(proc: subprocess.Popen, buffer: FrameBuffer,
                  shutdown_event: threading.Event):
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
    print("\n[!] FFmpeg process exited unexpectedly.")
    shutdown_event.set()


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

    monitor = choose_monitor(monitors)
    print(f"\nCapturing: {monitor.width}x{monitor.height} "
          f"at ({monitor.x}, {monitor.y}) @ {args.fps}fps\n")

    frame_buffer = FrameBuffer()
    shutdown_event = threading.Event()

    proc = start_ffmpeg(monitor, args.fps, args.quality)

    reader_thread = threading.Thread(
        target=ffmpeg_reader, args=(proc, frame_buffer, shutdown_event),
        daemon=True)
    reader_thread.start()

    # Monitor for unexpected FFmpeg exit in a background thread
    def watch_shutdown():
        shutdown_event.wait()
        print("[!] Initiating shutdown due to FFmpeg exit...")
        server.shutdown()

    threading.Thread(target=watch_shutdown, daemon=True).start()

    StreamHandler.frame_buffer = frame_buffer
    server = ThreadingHTTPServer(("0.0.0.0", args.port), StreamHandler)

    lan_ip = get_lan_ip()
    print(f"Stream live at http://{lan_ip}:{args.port}")
    print("Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        proc.terminate()
        proc.wait()
        server.shutdown()


if __name__ == "__main__":
    main()
