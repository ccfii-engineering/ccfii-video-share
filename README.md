# CCFII Display Share

CCFII Display Share is a Windows-first local network broadcast tool for sending a selected display or window to receiver devices on the same network. It is designed for church operations where volunteers and AV staff need a simple, branded broadcast console instead of command-line scripts.

## Development Run

1. Install Python 3.12 and FFmpeg on Windows.
2. Run:

```bash
python -m pip install -r requirements.txt
python launcher.py
```

For CLI troubleshooting, use:

```bash
python launcher.py --cli
```

## Windows Packaging

To build the packaged app and installer on Windows:

```powershell
.\build_installer.ps1
```

That script will:
- install PyInstaller
- generate an `.ico` from the CCFII logo if needed
- build `CCFIIDisplayShare.exe`
- compile the Inno Setup installer

## Project Structure

The real application code lives in `ccfii_display_share/`:

- `capture.py`: display discovery and FFmpeg capture lifecycle
- `streaming.py`: MJPEG parsing, frame buffering, and HTTP streaming
- `manager.py`: broadcast orchestration and runtime state
- `desktop.py`: branded desktop operator UI
- `cli.py`: legacy console workflow
- `launcher.py`: packaged launch entrypoint

The root folder is intentionally kept minimal:

- `run.bat`, `run.pyw`, `launcher.py`: Windows launch wrappers
- `desktop_app.py`, `server.py`: compatibility shims for packaging and legacy imports
- `CCFIIDisplayShare.spec`, `build_installer.ps1`, `installer/`: packaging assets

## Operator Flow

- Open the desktop app
- Select the display or window to share
- Start the broadcast
- Copy the receiver link to the device that will feed the destination monitor

## Verification

Run the automated checks:

```bash
python -m pytest tests/test_frame_parser.py -q
python -m pytest tests/test_startup.py -q
python -m pytest tests/test_desktop_app.py -q
```
