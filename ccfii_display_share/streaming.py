"""MJPEG parsing and HTTP streaming primitives."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from .config import STREAM_IDLE_RETRIES, STREAM_WAIT_TIMEOUT


JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


def extract_frames(data: bytes) -> tuple[list[bytes], bytes]:
    """Extract complete JPEG frames from a byte buffer."""
    frames = []
    while True:
        soi_pos = data.find(JPEG_SOI)
        if soi_pos == -1:
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
    """Thread-safe container for the latest MJPEG frame."""

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
    transition: opacity 0.3s;
  }
  .status:empty { opacity: 0; }
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
  let stallTimer = null;
  const STALL_TIMEOUT = 8000;

  function resetStallTimer() {
    clearTimeout(stallTimer);
    stallTimer = setTimeout(function() {
      img.removeAttribute("src");
      scheduleReconnect();
    }, STALL_TIMEOUT);
  }

  function scheduleReconnect() {
    clearTimeout(stallTimer);
    if (reconnectTimer !== null) return;
    status.textContent = "Disconnected. Reconnecting...";
    reconnectTimer = setTimeout(connectStream, retryDelay);
    retryDelay = Math.min(retryDelay * 2, 5000);
  }

  function connectStream() {
    reconnectTimer = null;
    status.textContent = "Connecting...";
    img.src = "/stream?ts=" + Date.now();
    resetStallTimer();
  }

  img.onload = function() {
    retryDelay = 1000;
    status.textContent = "";
    resetStallTimer();
  };

  img.onerror = function() {
    img.removeAttribute("src");
    scheduleReconnect();
  };

  window.addEventListener("online", connectStream);
  document.addEventListener("visibilitychange", function() {
    if (!document.hidden && !img.src) connectStream();
  });
  connectStream();
</script>
</body>
</html>"""


class StreamHandler(BaseHTTPRequestHandler):
    """HTTP handler that serves the viewer page and MJPEG stream."""

    frame_buffer: FrameBuffer
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
            pass
        finally:
            self.frame_buffer.remove_viewer()

    def log_message(self, format, *args):
        pass
