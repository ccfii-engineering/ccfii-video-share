# Display Share Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows tool that mirrors a selected display over the LAN as an MJPEG stream, viewable in any browser.

**Architecture:** A single Python script (`server.py`) launches FFmpeg to capture a chosen monitor via `gdigrab`, parses MJPEG frames from its stdout, and serves them over HTTP using `ThreadingHTTPServer`. Viewers open a URL and see a fullscreen `<img>` that streams natively. Batch scripts handle install and launch.

**Tech Stack:** Python 3.8+ stdlib (`http.server`, `threading`, `subprocess`, `argparse`, `ctypes`, `socket`, `atexit`), `screeninfo` (pip), FFmpeg (`gdigrab`), Windows batch scripts.

**Spec:** `docs/superpowers/specs/2026-04-02-display-share-design.md`

---

## File Structure

```
ccfii-video-share/
├── server.py            # Main application: capture, parse, serve
├── requirements.txt     # Python dependencies (screeninfo)
├── install.bat          # One-time setup: installs Python, FFmpeg, pip deps
├── run.bat              # Launches server.py
└── tests/
    └── test_frame_parser.py  # Unit tests for MJPEG frame extraction
```

`server.py` is intentionally a single file — keeps deployment dead simple (copy folder, run bat). Internal structure uses clear functions/classes, not module splits.

---

## Chunk 1: Core MJPEG Frame Parser

The frame parser is the trickiest part and the only piece that's unit-testable cross-platform. Build and test it first.

### Task 1: MJPEG Frame Parser — Test

**Files:**
- Create: `tests/test_frame_parser.py`

- [ ] **Step 1: Write failing tests for frame extraction**

```python
"""Tests for MJPEG frame extraction from raw byte stream."""
import unittest


def extract_frames(data: bytes) -> tuple[list[bytes], bytes]:
    """Extract complete JPEG frames from a byte buffer.

    Scans for SOI (0xFFD8) and EOI (0xFFD9) markers.
    Returns (list_of_complete_frames, remaining_bytes).
    """
    raise NotImplementedError


class TestExtractFrames(unittest.TestCase):
    SOI = b"\xff\xd8"
    EOI = b"\xff\xd9"

    def _make_frame(self, payload: bytes = b"JPEG_DATA") -> bytes:
        return self.SOI + payload + self.EOI

    def test_single_complete_frame(self):
        frame = self._make_frame()
        frames, remaining = extract_frames(frame)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0], frame)
        self.assertEqual(remaining, b"")

    def test_two_frames_back_to_back(self):
        f1 = self._make_frame(b"AAA")
        f2 = self._make_frame(b"BBB")
        frames, remaining = extract_frames(f1 + f2)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0], f1)
        self.assertEqual(frames[1], f2)

    def test_incomplete_frame_kept_in_remaining(self):
        complete = self._make_frame(b"DONE")
        partial = self.SOI + b"PARTIAL"
        frames, remaining = extract_frames(complete + partial)
        self.assertEqual(len(frames), 1)
        self.assertEqual(remaining, partial)

    def test_empty_input(self):
        frames, remaining = extract_frames(b"")
        self.assertEqual(frames, [])
        self.assertEqual(remaining, b"")

    def test_garbage_before_first_soi(self):
        garbage = b"\x00\x01\x02"
        frame = self._make_frame()
        frames, remaining = extract_frames(garbage + frame)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0], frame)

    def test_no_complete_frame(self):
        partial = self.SOI + b"WAITING"
        frames, remaining = extract_frames(partial)
        self.assertEqual(frames, [])
        self.assertEqual(remaining, partial)

    def test_trailing_ff_preserved(self):
        """A trailing 0xFF could be half of a SOI split across chunks."""
        data = b"\x00\x01\xff"
        frames, remaining = extract_frames(data)
        self.assertEqual(frames, [])
        self.assertEqual(remaining, b"\xff")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_frame_parser.py -v`
Expected: FAIL — `NotImplementedError`

- [ ] **Step 3: Commit test file**

```bash
git add tests/test_frame_parser.py
git commit -m "test: add MJPEG frame parser tests"
```

### Task 2: MJPEG Frame Parser — Implementation

**Files:**
- Create: `server.py` (start with just the parser function)
- Modify: `tests/test_frame_parser.py` (import from server.py)

- [ ] **Step 1: Implement `extract_frames` in server.py**

```python
"""CCFII Display Share — Mirror a Windows display over LAN via MJPEG."""

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
```

- [ ] **Step 2: Update test imports**

In `tests/test_frame_parser.py`, replace the local stub:

```python
# Replace the local extract_frames stub and NotImplementedError with:
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from server import extract_frames
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `python -m pytest tests/test_frame_parser.py -v`
Expected: All 7 tests PASS

- [ ] **Step 4: Commit**

```bash
git add server.py tests/test_frame_parser.py
git commit -m "feat: implement MJPEG frame parser with SOI/EOI scanning"
```

---

## Chunk 2: Shared Frame Buffer + HTTP Server

### Task 3: Shared Frame Buffer

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add `FrameBuffer` class to server.py**

This is a thread-safe buffer that holds the latest frame. Multiple HTTP handler threads read from it; the FFmpeg reader thread writes to it.

```python
import threading


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
```

- [ ] **Step 2: Commit**

```bash
git add server.py
git commit -m "feat: add thread-safe FrameBuffer for sharing frames across handlers"
```

### Task 4: HTTP Server + Viewer HTML

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add viewer HTML constant**

```python
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
```

- [ ] **Step 2: Add `StreamHandler` class**

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat: add HTTP server with MJPEG streaming and viewer HTML"
```

---

## Chunk 3: FFmpeg Capture + Display Selection + Main

### Task 5: Display Detection

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add display listing function**

```python
import sys
import ctypes


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
```

- [ ] **Step 2: Commit**

```bash
git add server.py
git commit -m "feat: add DPI-aware display detection and selection"
```

### Task 6: FFmpeg Subprocess + Frame Reader

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add FFmpeg launcher and reader thread**

```python
import subprocess


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
```

- [ ] **Step 2: Commit**

```bash
git add server.py
git commit -m "feat: add FFmpeg capture subprocess and frame reader thread"
```

### Task 7: Main Entry Point + CLI Args

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Add argument parser and main function**

```python
import argparse
import socket


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
```

- [ ] **Step 2: Run a quick syntax check**

Run: `python -c "import ast; ast.parse(open('server.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add server.py
git commit -m "feat: add CLI args, display selection, and main entry point"
```

---

## Chunk 4: Installer Scripts

### Task 8: requirements.txt

**Files:**
- Create: `requirements.txt`

- [ ] **Step 1: Create requirements.txt**

```
screeninfo
```

- [ ] **Step 2: Commit**

```bash
git add requirements.txt
git commit -m "chore: add requirements.txt"
```

### Task 9: install.bat

**Files:**
- Create: `install.bat`

- [ ] **Step 1: Write install.bat**

```batch
@echo off
echo ============================================
echo   CCFII Display Share — Installer
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Python not found. Installing via winget...
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    echo [!] Please restart this script after Python installs.
    pause
    exit /b 1
) else (
    echo [OK] Python found.
)

:: Check FFmpeg
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] FFmpeg not found. Installing via winget...
    winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    echo [!] Please restart this script after FFmpeg installs.
    pause
    exit /b 1
) else (
    echo [OK] FFmpeg found.
)

:: Install Python dependencies
echo [*] Installing Python dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [!] pip install failed.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Installation complete!
echo   Run "run.bat" to start sharing.
echo ============================================
pause
```

- [ ] **Step 2: Commit**

```bash
git add install.bat
git commit -m "chore: add install.bat for one-click Windows setup"
```

### Task 10: run.bat

**Files:**
- Create: `run.bat`

- [ ] **Step 1: Write run.bat**

```batch
@echo off
echo Starting Display Share...
echo.
python server.py %*
if %errorlevel% neq 0 (
    echo.
    echo [!] Server exited with an error.
)
pause
```

- [ ] **Step 2: Commit**

```bash
git add run.bat
git commit -m "chore: add run.bat launcher"
```

---

## Chunk 5: Final Verification

### Task 11: Verify Everything

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All 7 frame parser tests PASS

- [ ] **Step 2: Verify server.py syntax**

Run: `python -c "import ast; ast.parse(open('server.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify file structure is complete**

```
ccfii-video-share/
├── server.py
├── requirements.txt
├── install.bat
├── run.bat
├── tests/
│   └── test_frame_parser.py
└── docs/
```

- [ ] **Step 4: Final commit if any changes**

```bash
git add -A
git commit -m "chore: finalize display share tool"
```

---

## Deployment Instructions

On the Windows machine:

1. Copy the `ccfii-video-share/` folder to the machine
2. Double-click `install.bat` (one time only)
3. Double-click `run.bat`
4. Pick the display number
5. On the Android TV browser, go to `http://<windows-ip>:8080`
