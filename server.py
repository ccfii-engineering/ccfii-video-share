"""CCFII Display Share — Mirror a Windows display over LAN via MJPEG."""

import threading

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


from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


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
