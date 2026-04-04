# CCFII Display Share Desktop App Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a branded Windows desktop app for CCFII Display Share that replaces the batch-script workflow with an operator-friendly control panel and installer packaging path.

**Architecture:** Keep the existing FFmpeg + MJPEG streaming engine in Python, but refactor it behind a reusable broadcast manager that can be driven by either the CLI or a desktop UI. Build a Tkinter desktop shell with a simple-first operator experience, then add Windows packaging assets so the app can be distributed as a normal installer instead of `run.bat`.

**Tech Stack:** Python 3.12, Tkinter, `http.server`, `threading`, `subprocess`, `screeninfo`, FFmpeg, PyInstaller, Inno Setup.

---

### Task 1: Broadcast Manager Extraction

**Files:**
- Modify: `server.py`
- Test: `tests/test_startup.py`

**Step 1: Write the failing tests**

Add tests for a reusable manager that:
- starts a selected capture target and HTTP server without prompting in the console
- exposes the viewer URL and current target
- stops cleanly and tears down capture/server threads

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_startup.py -q`
Expected: FAIL because the reusable manager API does not exist yet.

**Step 3: Write minimal implementation**

Refactor `server.py` to add a `BroadcastManager` class that:
- receives targets, port, fps, and quality
- starts/stops the server lifecycle programmatically
- keeps the existing CLI entry point working

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_startup.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add server.py tests/test_startup.py
git commit -m "feat: add reusable broadcast manager for desktop integration"
```

### Task 2: Viewer and Runtime Status Improvements

**Files:**
- Modify: `server.py`
- Test: `tests/test_startup.py`

**Step 1: Write the failing tests**

Add tests for:
- viewer count access from the frame buffer
- idle stream disconnect behavior that allows reconnect
- manager status fields needed by the desktop UI

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_startup.py -q`
Expected: FAIL because the new status APIs do not exist yet.

**Step 3: Write minimal implementation**

Expose:
- current viewer count
- current stream URL
- current capture target label
- broadcast running state

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_startup.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add server.py tests/test_startup.py
git commit -m "feat: expose runtime status for desktop operator UI"
```

### Task 3: Desktop App UI

**Files:**
- Create: `desktop_app.py`
- Create: `assets/ccfii-logo.png`
- Modify: `requirements.txt`

**Step 1: Write the failing tests**

Add targeted tests for desktop helpers that can be exercised without opening a full GUI, such as:
- target label formatting
- status text generation
- validation of advanced settings input

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_desktop_app.py -q`
Expected: FAIL because `desktop_app.py` does not exist yet.

**Step 3: Write minimal implementation**

Create a desktop app with:
- CCFII branding and logo
- source selector
- start/stop broadcast controls
- receiver link card
- live status card
- advanced AV settings drawer

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_desktop_app.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add desktop_app.py assets/ccfii-logo.png tests/test_desktop_app.py
git commit -m "feat: add branded CCFII desktop control app"
```

### Task 4: Launch and Compatibility Scripts

**Files:**
- Modify: `run.bat`
- Create: `run.pyw`
- Create: `launcher.py`
- Test: `tests/test_startup.py`

**Step 1: Write the failing tests**

Add tests that verify:
- the launcher defaults to the desktop app
- the existing CLI path remains available for fallback/troubleshooting

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_startup.py -q`
Expected: FAIL because the launcher behavior has not been updated yet.

**Step 3: Write minimal implementation**

Add a Windows-friendly launcher that opens the desktop app without an attached console, while preserving an explicit CLI fallback.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_startup.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add run.bat run.pyw launcher.py tests/test_startup.py
git commit -m "feat: route launches through the desktop app"
```

### Task 5: Windows Installer Assets

**Files:**
- Create: `installer/CCFIIDisplayShare.iss`
- Create: `build_installer.ps1`
- Create: `CCFIIDisplayShare.spec`
- Modify: `install.bat`

**Step 1: Write the failing tests**

Add tests that verify:
- packaging scripts reference the desktop launcher instead of `server.py`
- installer metadata uses the CCFII app name and assets

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_startup.py -q`
Expected: FAIL because installer assets do not exist yet.

**Step 3: Write minimal implementation**

Add:
- PyInstaller spec for bundling the app and logo
- Inno Setup script for a Windows installer
- PowerShell build script that assembles the package
- updated `install.bat` messaging that points to installer-based distribution

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_startup.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add installer/CCFIIDisplayShare.iss build_installer.ps1 CCFIIDisplayShare.spec install.bat tests/test_startup.py
git commit -m "build: add Windows packaging and installer assets"
```

### Task 6: Documentation and Verification

**Files:**
- Create: `README.md`
- Modify: `docs/plans/2026-04-05-display-share-desktop-app.md`

**Step 1: Write the verification checklist**

Document:
- how to run the desktop app in development
- how to build the packaged app
- how to create the Windows installer
- what to test on a real LAN device

**Step 2: Run verification**

Run:
- `python -m pytest tests/test_startup.py -q`
- `python -m pytest tests/test_frame_parser.py -q`
- `python -m pytest tests/test_desktop_app.py -q`

Expected: PASS

**Step 3: Commit**

```bash
git add README.md docs/plans/2026-04-05-display-share-desktop-app.md
git commit -m "docs: add desktop app setup and packaging guide"
```
