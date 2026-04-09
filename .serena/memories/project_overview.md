# CCFII Display Share

Windows-first (macOS supported) local network broadcast tool that sends a selected display or window to receiver devices on the same network. Built for church AV operations — a branded desktop console as an alternative to CLI scripts.

## Purpose
- Operator selects a display/window, starts broadcast, shares a receiver link with destination devices
- Uses FFmpeg to capture, MJPEG over HTTP to stream frames

## Tech Stack
- Python 3.12
- PySide6 (desktop UI)
- FFmpeg (subprocess, bundled in Windows build)
- Pillow, mss, screeninfo
- PyInstaller for packaging (Windows .exe + Inno Setup installer; macOS .app + .icns)
- pytest for tests

## Codebase Structure
Root is intentionally minimal. Real code lives in `ccfii_display_share/`:
- `capture.py` / `capture/` — display discovery & FFmpeg capture lifecycle
- `streaming.py` — MJPEG parsing, frame buffering, HTTP streaming
- `manager.py` — broadcast orchestration & runtime state
- `desktop.py` — branded PySide6 operator UI
- `cli.py` — legacy console workflow
- `launcher.py` — packaged launch entrypoint
- `config.py`, `contracts.py`

Root files:
- `desktop_app.py`, `server.py` — compatibility shims for packaging/legacy imports
- `launcher.py`, `run.bat`, `run.pyw` — launch wrappers
- `CCFIIDisplayShare.spec`, `build_installer.ps1`, `build.bat`, `installer/` — packaging
- `.github/workflows/` — CI (cross-platform release publishing)
- `assets/` — logos
- `tests/` — `test_frame_parser.py`, `test_startup.py`, `test_desktop_app.py`
