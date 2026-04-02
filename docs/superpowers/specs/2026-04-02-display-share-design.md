# Display Share — Design Spec

## Purpose

Mirror a selected Windows display over the local network so Android TVs (and any browser-equipped device) can show a live, smooth preview — used as a duplicate prompter/presentation display.

## Architecture

```
Windows Machine                        LAN                     Android TV / Browser
┌──────────────────────┐                                 ┌────────────────────────┐
│  run.bat              │                                 │  Browser (fullscreen)   │
│    → Python server.py │                                 │                         │
│    → spawns FFmpeg    │──── HTTP :8080 ────────────────│  GET /                  │
│      (gdigrab capture │     MJPEG stream               │    → viewer.html        │
│       @ 30fps)        │                                 │  <img src="/stream">    │
│    → serves /stream   │                                 │    → native MJPEG       │
└──────────────────────┘                                 └────────────────────────┘
```

## Components

### 1. server.py — Main application

**Display detection:**
- Uses Python `screeninfo` to enumerate monitors
- Calls `ctypes.windll.user32.SetProcessDPIAware()` before querying to get physical pixel coordinates (avoids DPI scaling mismatch with gdigrab)
- Presents numbered list in console, user picks one
- Captures monitor offset/resolution in physical pixels for FFmpeg targeting

**FFmpeg subprocess:**
- Launches: `ffmpeg -f gdigrab -framerate 30 -offset_x {x} -offset_y {y} -video_size {w}x{h} -i desktop -f mjpeg -q:v 5 -`
- Reads MJPEG frames from stdout pipe by scanning for JPEG SOI (`\xff\xd8`) and EOI (`\xff\xd9`) markers to delimit individual frames
- Each extracted frame is pushed to a shared buffer that HTTP handler threads read from
- `-q:v 5` balances quality/bandwidth (1=best, 31=worst)
- Framerate configurable via command-line arg, default 30
- On server shutdown (Ctrl+C / `atexit`), the FFmpeg subprocess is explicitly terminated via `process.terminate()` wrapped in `try/finally` to prevent orphaned processes
- If FFmpeg exits unexpectedly, server logs the error and exits cleanly

**HTTP server (ThreadingHTTPServer):**
- Uses `ThreadingHTTPServer` (not single-threaded `HTTPServer`) to support multiple concurrent streaming clients
- `GET /` — serves the viewer HTML page
- `GET /stream` — serves MJPEG multipart stream (`Content-Type: multipart/x-mixed-replace; boundary=frame`)
- Binds to `0.0.0.0:8080`

**Console output:**
- Prints LAN IP + URL on startup (e.g., `Stream live at http://192.168.1.50:8080`)
- Shows connected viewer count

### 2. Viewer HTML (inline in server.py)

- Black background, no margins, no scrollbars
- Single `<img>` tag: `width: 100vw; height: 100vh; object-fit: contain`
- No JavaScript needed — browser handles MJPEG natively via `<img src="/stream">`
- `<meta>` viewport tag for proper scaling on TVs

### 3. install.bat

1. Check if Python 3 is installed (`python --version`)
2. If not, install via `winget install Python.Python.3.12`
3. Check if FFmpeg is installed (`ffmpeg -version`)
4. If not, install via `winget install Gyan.FFmpeg`
5. Run `pip install -r requirements.txt`
6. Print success message

### 4. run.bat

1. Run `python server.py`
2. Keeps console open on error

### 5. requirements.txt

```
screeninfo
```

## File Structure

```
ccfii-video-share/
├── install.bat
├── run.bat
├── server.py
├── requirements.txt
└── docs/
```

## Key Decisions

- **MJPEG over H.264**: MJPEG requires no client-side decoder, works natively in `<img>` tags on every browser. On LAN, bandwidth is not a constraint.
- **FFmpeg for capture**: Native Windows `gdigrab` gives smooth, efficient screen capture at configurable FPS. Much better than Python-based screenshot loops.
- **No WebSocket/WebRTC**: Unnecessary complexity for a LAN MJPEG stream to a browser.
- **screeninfo for monitor detection**: Lightweight Python package to list monitors with coordinates, which FFmpeg needs for targeting a specific display.
- **ThreadingHTTPServer**: Uses Python's built-in `ThreadingHTTPServer` to handle multiple concurrent viewers. No need for Flask or external web framework.

## Configuration

All via command-line args to `server.py`:
- `--port 8080` (default 8080)
- `--fps 30` (default 30)
- `--quality 5` (JPEG quality 1-31, default 5)

## Constraints

- Windows only (gdigrab is Windows-specific)
- Requires Python 3.8+ and FFmpeg on the Windows machine
- Viewer requires a browser that supports MJPEG (all modern browsers do)
- LAN only — no authentication or encryption (not needed for local network use)
