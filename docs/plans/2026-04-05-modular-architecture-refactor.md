# Modular Architecture Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor CCFII Display Share into a clean modular Python package so the project has clear boundaries between capture, streaming, desktop UI, launchers, and packaging.

**Architecture:** Move application logic into a `ccfii_display_share` package with focused modules for streaming, capture lifecycle, orchestration, desktop UI, and CLI entry points. Keep root-level files only as thin compatibility wrappers for Windows launch scripts and tests.

**Tech Stack:** Python 3.12, Tkinter, `http.server`, `threading`, `subprocess`, `screeninfo`, FFmpeg, PyInstaller, Inno Setup.

---

### Task 1: Define Package Boundaries

**Files:**
- Create: `ccfii_display_share/__init__.py`
- Create: `ccfii_display_share/config.py`
- Create: `ccfii_display_share/streaming.py`
- Create: `ccfii_display_share/capture.py`
- Create: `ccfii_display_share/manager.py`
- Test: `tests/test_startup.py`

**Step 1: Write the failing test**

Add a test proving the package exists and that the legacy `server` module can still access the main public APIs through it.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_startup.py -q`
Expected: FAIL because the package modules do not exist yet.

**Step 3: Write minimal implementation**

Create the package and move the streaming, capture, and orchestration code into dedicated modules.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_startup.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add ccfii_display_share tests/test_startup.py
git commit -m "refactor: create modular application package"
```

### Task 2: Move Desktop App into the Package

**Files:**
- Create: `ccfii_display_share/desktop.py`
- Modify: `desktop_app.py`
- Test: `tests/test_desktop_app.py`

**Step 1: Write the failing test**

Add a test proving the root `desktop_app.py` module is now only a compatibility wrapper around the packaged desktop implementation.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_desktop_app.py -q`
Expected: FAIL because the packaged desktop module does not exist yet.

**Step 3: Write minimal implementation**

Move the real desktop UI into `ccfii_display_share/desktop.py` and leave `desktop_app.py` as a thin re-export.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_desktop_app.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add ccfii_display_share/desktop.py desktop_app.py tests/test_desktop_app.py
git commit -m "refactor: move desktop UI into application package"
```

### Task 3: Create Proper Packaged Entry Points

**Files:**
- Create: `ccfii_display_share/cli.py`
- Create: `ccfii_display_share/launcher.py`
- Modify: `server.py`
- Modify: `launcher.py`
- Modify: `run.pyw`
- Test: `tests/test_startup.py`

**Step 1: Write the failing test**

Add a test proving the root launch files are wrappers around packaged entry points instead of holding application logic.

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_startup.py -q`
Expected: FAIL because the packaged entry points are not wired yet.

**Step 3: Write minimal implementation**

Move the CLI and launcher logic into the package and reduce root files to wrappers.

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_startup.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add ccfii_display_share/cli.py ccfii_display_share/launcher.py server.py launcher.py run.pyw tests/test_startup.py
git commit -m "refactor: isolate entry points behind packaged launchers"
```

### Task 4: Documentation and Cleanup

**Files:**
- Modify: `README.md`
- Modify: `docs/plans/2026-04-05-display-share-desktop-app.md`
- Modify: `docs/plans/2026-04-05-modular-architecture-refactor.md`

**Step 1: Document the new structure**

Add a short project layout section and explain which root files are only compatibility/packaging wrappers.

**Step 2: Run verification**

Run:
- `python -m pytest tests/test_startup.py -q`
- `python -m pytest tests/test_desktop_app.py -q`
- `python -m pytest tests/test_frame_parser.py -q`

Expected: PASS

**Step 3: Commit**

```bash
git add README.md docs/plans
git commit -m "docs: describe modular project structure"
```
