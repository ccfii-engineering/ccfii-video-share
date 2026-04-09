# CCFII Display Share

Windows-first (macOS supported) local network broadcast tool that sends a selected display or window to receiver devices on the same network. Built for church AV operations — a branded desktop console as an alternative to CLI scripts.

## Purpose
- Operator selects a display/window, starts broadcast, shares a receiver link with destination devices
- Uses FFmpeg to capture, MJPEG over HTTP to stream frames
- HTTP server exposes three routes: `/` (viewer page), `/stream` (MJPEG multipart feed), `/health` (JSON diagnostic payload)

## Tech Stack
- Python 3.12
- PySide6 (desktop UI)
- FFmpeg (subprocess, bundled in Windows build)
- Pillow, mss, screeninfo
- PyInstaller for packaging (Windows .exe + Inno Setup installer; macOS .app + .icns)
- pytest for tests

## Codebase Structure
Root is intentionally minimal. Real code lives in `ccfii_display_share/`:
- `capture/__init__.py` — display discovery, FFmpeg capture lifecycle, `CaptureController`, preview paths. ~600 lines; prefer symbolic tools.
- `capture/backends/{windows,macos}.py` — platform-specific capture backends
- `streaming.py` — MJPEG parsing, `FrameBuffer` (tracks `last_frame_age_seconds` / `has_frame`), `StreamHandler` (serves `/`, `/stream`, `/health`), `VIEWER_HTML` (browser receiver). Reconnect is driven solely by `img.onerror` — no client-side stall timer, no server idle-break. `/health` is diagnostic only and must not be polled by the viewer.
- `manager.py` — `BroadcastManager` orchestration & runtime state. Wires `frame_buffer` and `status_provider` into the handler class on start.
- `desktop.py` — branded PySide6 operator UI (`DisplayShareDesktopApp`, `launch_app`)
- `cli.py` — legacy console workflow
- `launcher.py` — packaged launch entrypoint
- `config.py`, `contracts.py`

Root files:
- `desktop_app.py`, `server.py` — compatibility shims for packaging/legacy imports. `server.py` re-exports widely used package symbols; `tests/test_startup.py` imports via `server.X`, so new public symbols must be re-exported there.
- `launcher.py`, `run.bat`, `run.pyw` — launch wrappers
- `CCFIIDisplayShare.spec`, `build_installer.ps1`, `build.bat`, `installer/` — packaging
- `.github/workflows/` — CI (cross-platform release publishing)
- `assets/` — logos
- `tests/` — `test_frame_parser.py`, `test_startup.py`, `test_desktop_app.py`
