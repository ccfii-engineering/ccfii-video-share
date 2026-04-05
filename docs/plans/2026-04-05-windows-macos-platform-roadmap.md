# Windows and macOS Platform Roadmap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Evolve CCFII Display Share from a Windows-only implementation into a clean Windows-and-macOS desktop product with shared UI/runtime behavior and platform-specific capture backends.

**Architecture:** Keep the operator experience, broadcast manager, MJPEG server, diagnostics, and packaging conventions in shared modules, but move source discovery and capture into backend adapters selected by the current operating system. Windows remains the reference platform and must be stabilized first, then the same backend contract is used to bring up macOS with honest capability and permission reporting.

**Tech Stack:** Python 3.12, PySide6, `http.server`, `threading`, `subprocess`, `screeninfo`, Pillow, `mss`, FFmpeg, PyInstaller, Inno Setup, macOS screen-recording permissions.

---

### Task 1: Document the Shared Backend Contract

**Files:**
- Create: `docs/plans/2026-04-05-windows-macos-platform-roadmap.md`
- Create: `ccfii_display_share/capture/contracts.py`
- Test: `tests/test_startup.py`

**Step 1: Write the failing test**

Add a test proving there is a platform backend contract entrypoint that can answer:
- list displays
- list windows
- capture preview
- start capture
- stop capture
- report platform capabilities and errors

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_startup.py -q`
Expected: FAIL because the backend contract module does not exist yet.

**Step 3: Write minimal implementation**

Create a contract module that defines the minimal shared interface for capture backends and a normalized capability/status shape the UI can consume.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_startup.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add docs/plans/2026-04-05-windows-macos-platform-roadmap.md ccfii_display_share/capture/contracts.py tests/test_startup.py
git commit -m "refactor: define platform capture backend contract"
```

### Task 2: Extract the Windows Backend Behind the Contract

**Files:**
- Create: `ccfii_display_share/capture/backends/__init__.py`
- Create: `ccfii_display_share/capture/backends/windows.py`
- Modify: `ccfii_display_share/capture.py`
- Test: `tests/test_startup.py`

**Step 1: Write the failing test**

Add tests proving the app can resolve a Windows backend and that existing Windows display/window discovery still routes through that backend rather than directly from the monolithic capture module.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_startup.py -q`
Expected: FAIL because there is no backend routing layer yet.

**Step 3: Write minimal implementation**

Move the current Windows-specific logic into `capture/backends/windows.py` and let the shared capture module delegate through the backend contract.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_startup.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add ccfii_display_share/capture.py ccfii_display_share/capture/backends tests/test_startup.py
git commit -m "refactor: route windows capture through backend adapter"
```

### Task 3: Stabilize Windows as the Reference Platform

**Files:**
- Modify: `ccfii_display_share/capture/backends/windows.py`
- Modify: `ccfii_display_share/manager.py`
- Modify: `ccfii_display_share/desktop.py`
- Test: `tests/test_startup.py`
- Test: `tests/test_desktop_app.py`

**Step 1: Write the failing test**

Add tests for the Windows reference behavior:
- display preview uses the native desktop path
- window capture fails fast when FFmpeg exits immediately
- manager status reflects actual backend health
- diagnostics keep a user-copyable log of preview and broadcast failures

**Step 2: Run test to verify it fails**

Run:
- `python -m pytest tests/test_startup.py -q`
- `python -m pytest tests/test_desktop_app.py -q`

Expected: FAIL until the backend and UI state are aligned.

**Step 3: Write minimal implementation**

Finish Windows hardening so it becomes the known-good baseline for:
- preview reliability
- display and window capture
- honest broadcast status
- diagnostics and operator troubleshooting
- packaging/runtime dependency checks

**Step 4: Run test to verify it passes**

Run:
- `python -m pytest tests/test_startup.py -q`
- `python -m pytest tests/test_desktop_app.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add ccfii_display_share/capture/backends/windows.py ccfii_display_share/manager.py ccfii_display_share/desktop.py tests/test_startup.py tests/test_desktop_app.py
git commit -m "fix: stabilize windows capture backend and diagnostics"
```

### Task 4: Add Backend Capability Reporting to the UI

**Files:**
- Modify: `ccfii_display_share/desktop.py`
- Modify: `ccfii_display_share/manager.py`
- Modify: `ccfii_display_share/capture/contracts.py`
- Test: `tests/test_desktop_app.py`

**Step 1: Write the failing test**

Add tests proving the UI can render:
- supported source types
- missing capability messages
- permission/setup requirements
- platform-aware diagnostics copy text

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_desktop_app.py -q`
Expected: FAIL because the UI does not yet consume backend capability metadata.

**Step 3: Write minimal implementation**

Expose backend capabilities through the manager and use them in the desktop UI so the app can honestly show what is available on the current OS.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_desktop_app.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add ccfii_display_share/desktop.py ccfii_display_share/manager.py ccfii_display_share/capture/contracts.py tests/test_desktop_app.py
git commit -m "feat: surface backend capabilities in desktop ui"
```

### Task 5: Add a macOS Backend Skeleton

**Files:**
- Create: `ccfii_display_share/capture/backends/macos.py`
- Modify: `ccfii_display_share/capture/backends/__init__.py`
- Modify: `ccfii_display_share/capture/contracts.py`
- Test: `tests/test_startup.py`

**Step 1: Write the failing test**

Add tests proving a macOS backend can be resolved and can report:
- display capture support
- window capture support status
- required screen-recording permission messaging

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_startup.py -q`
Expected: FAIL because the macOS backend module and capability contract do not exist yet.

**Step 3: Write minimal implementation**

Create a macOS backend skeleton that reports supported and unsupported features clearly, even before full capture support is implemented.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_startup.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add ccfii_display_share/capture/backends/macos.py ccfii_display_share/capture/backends/__init__.py ccfii_display_share/capture/contracts.py tests/test_startup.py
git commit -m "feat: add macos capture backend scaffold"
```

### Task 6: Bring Up macOS Display Capture First

**Files:**
- Modify: `ccfii_display_share/capture/backends/macos.py`
- Modify: `ccfii_display_share/desktop.py`
- Modify: `requirements.txt`
- Test: `tests/test_startup.py`
- Test: `tests/test_desktop_app.py`

**Step 1: Write the failing test**

Add tests proving the macOS backend can:
- list displays
- capture a preview for a display source
- report permission-denied states in a normalized way

**Step 2: Run test to verify it fails**

Run:
- `python -m pytest tests/test_startup.py -q`
- `python -m pytest tests/test_desktop_app.py -q`

Expected: FAIL because macOS display capture is not implemented yet.

**Step 3: Write minimal implementation**

Implement the first supported macOS path:
- display capture only
- clear onboarding for Screen Recording permission
- diagnostics that guide the operator to System Settings when capture is blocked

**Step 4: Run test to verify it passes**

Run:
- `python -m pytest tests/test_startup.py -q`
- `python -m pytest tests/test_desktop_app.py -q`

Expected: PASS

**Step 5: Commit**

```bash
git add ccfii_display_share/capture/backends/macos.py ccfii_display_share/desktop.py requirements.txt tests/test_startup.py tests/test_desktop_app.py
git commit -m "feat: add macos display capture support"
```

### Task 7: Package for Both Supported Platforms

**Files:**
- Modify: `CCFIIDisplayShare.spec`
- Modify: `.github/workflows/release-desktop-apps.yml`
- Create: `.github/workflows/build-macos.yml`
- Modify: `README.md`
- Test: `tests/test_startup.py`

**Step 1: Write the failing test**

Add tests proving the repo contains:
- Windows packaging/build flow
- macOS packaging/build flow
- docs explaining platform-specific requirements

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_startup.py -q`
Expected: FAIL because macOS packaging docs/workflow do not exist yet.

**Step 3: Write minimal implementation**

Add a macOS build workflow, update documentation for both supported platforms, and make sure packaging paths remain explicit and maintainable.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_startup.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add CCFIIDisplayShare.spec .github/workflows README.md tests/test_startup.py
git commit -m "build: document and automate windows and macos packaging"
```

### Task 8: Cross-Platform Verification Pass

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-04-05-windows-macos-platform-roadmap.md`

**Step 1: Write the verification checklist**

Document the manual verification matrix for:
- Windows display capture
- Windows window capture
- Windows portable and installer builds
- macOS display capture
- macOS permission onboarding
- diagnostics copy/paste workflow

**Step 2: Run verification**

Run:
- `python -m pytest tests/test_startup.py -q`
- `python -m pytest tests/test_desktop_app.py -q`
- `python -m pytest tests/test_frame_parser.py -q`

Expected: PASS

**Step 3: Commit**

```bash
git add README.md docs/plans/2026-04-05-windows-macos-platform-roadmap.md
git commit -m "docs: add windows and macos verification matrix"
```
