# Suggested Commands

## Setup
```bash
python -m pip install -r requirements.txt
```
Requires Python 3.12 and FFmpeg installed.

## Run (development)
```bash
python launcher.py           # desktop UI
python launcher.py --cli     # legacy CLI for troubleshooting
```

## Tests
```bash
python -m pytest tests/test_frame_parser.py -q
python -m pytest tests/test_startup.py -q
python -m pytest tests/test_desktop_app.py -q
```
Or run all: `python -m pytest -q`

## Build — Windows
```powershell
.\build_installer.ps1
```
or `build.bat` — installs PyInstaller, bundles ffmpeg.exe, builds .exe, compiles Inno Setup installer.

## Build — macOS
See README.md "macOS Packaging" — uses sips + iconutil to make .icns, then PyInstaller `--windowed`, ad-hoc codesign, ditto zip.

## System (Darwin)
Standard macOS/BSD tools. Note: `sed -i` requires an empty string arg (`sed -i ''`). Use `sips` and `iconutil` for macOS icon workflow. `ditto` for zipping app bundles preserving metadata.

## Git
Standard git. Current branch: `master` (main branch). User: PaoloTolentino.
