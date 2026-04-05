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

Or use the batch wrapper:

```bat
build.bat
```

That script will:
- install PyInstaller
- generate an `.ico` from the CCFII logo if needed
- install or resolve FFmpeg, then bundle `ffmpeg.exe` into the app
- build `CCFIIDisplayShare.exe`
- compile the Inno Setup installer

## macOS Packaging

To build the packaged macOS app and archive:

```bash
python -m pip install -r requirements.txt
sips -z 512 512 assets/ccfii-logo.png --out assets/ccfii-logo-512.png
mkdir -p build/macos-icon.iconset
cp assets/ccfii-logo-512.png build/macos-icon.iconset/icon_512x512.png
cp assets/ccfii-logo-512.png build/macos-icon.iconset/icon_512x512@2x.png
iconutil -c icns build/macos-icon.iconset -o assets/ccfii-logo.icns
python -m PyInstaller --noconfirm --windowed --name CCFIIDisplayShare --icon assets/ccfii-logo.icns --add-data "assets/ccfii-logo.png:assets" desktop_app.py
codesign --force --deep --sign - dist/CCFIIDisplayShare.app
ditto -c -k --keepParent dist/CCFIIDisplayShare.app dist/CCFIIDisplayShare-macos.zip
```

The macOS build flow:
- produces a `.app` bundle with the same desktop UI
- packages the CCFII logo with the app
- generates a `.icns` app icon from the CCFII logo
- keeps display preview available through the macOS backend
- may require `Screen Recording` permission for preview capture
- does not yet enable live macOS display broadcasting

If macOS warns that the app "developer cannot be verified," use Finder to `Right-click -> Open` the app once and confirm the prompt. The workflow now ad-hoc signs the bundle, but it is still not notarized.

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
- `.github/workflows/build-macos.yml`: macOS packaging workflow

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

## Manual Verification Matrix

- Windows display capture
- Windows window capture
- Windows portable build
- Windows installer build
- macOS display capture
- macOS Screen Recording permission onboarding
- Diagnostics copy and paste workflow
