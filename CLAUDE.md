# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

CCFII Display Share is a Windows-first (macOS supported) LAN broadcast tool that captures a display or window with FFmpeg and streams MJPEG over HTTP to receiver devices on the same network. It is used by church AV operators, so the desktop app is the primary surface; the CLI is a legacy troubleshooting path.

## Commands

Requires Python 3.12 and FFmpeg on PATH (Windows builds bundle `ffmpeg.exe`).

```bash
python -m pip install -r requirements.txt
python launcher.py               # launch desktop UI
python launcher.py --cli         # legacy CLI flow
```

Tests (pytest):

```bash
python -m pytest -q                              # all tests
python -m pytest tests/test_frame_parser.py -q   # single file
python -m pytest tests/test_startup.py -q
python -m pytest tests/test_desktop_app.py -q
python -m pytest tests/test_desktop_app.py::<name> -q   # single test
```

No linter/formatter is configured — match surrounding style.

### Packaging

- Windows: `./build_installer.ps1` (or `build.bat`) — installs PyInstaller, resolves/bundles `ffmpeg.exe`, builds `CCFIIDisplayShare.exe` via `CCFIIDisplayShare.spec`, then compiles the Inno Setup installer under `installer/`.
- macOS: see the "macOS Packaging" block in `README.md`. Flow is `sips` + `iconutil` to produce `.icns`, then `python -m PyInstaller --windowed --icon ... desktop_app.py`, ad-hoc `codesign`, `ditto` zip. The macOS build does **not yet enable live display broadcasting** — preview capture works and requires Screen Recording permission.

## Architecture

The root directory is deliberately thin. `desktop_app.py`, `server.py`, and the top-level `launcher.py` are **compatibility shims** that only re-export from the `ccfii_display_share/` package — they exist for PyInstaller entry points and legacy imports. Never add real logic to those shims; extend the package instead.

The real pipeline is layered inside `ccfii_display_share/`:

1. **`capture/`** — capture backend abstraction. `capture/__init__.py` exposes `CaptureTarget`, `CaptureController`, backend resolution (`resolve_capture_backend`), target enumeration (`list_monitors` / `list_windows` / `build_capture_targets`), and the FFmpeg lifecycle (`start_ffmpeg`, `stop_ffmpeg`, reader threads). Platform specifics live in `capture/backends/windows.py` and `capture/backends/macos.py`. Preview still-capture has its own path (`capture_preview_image`, `encode_screenshot_frame`) that does not require FFmpeg, which is why preview works on macOS even though live broadcast does not.

2. **`streaming.py`** — MJPEG byte-stream parsing (`extract_frames` splits on JPEG SOI/EOI markers), `FrameBuffer` holds the latest frame (and tracks `last_frame_age_seconds` / `has_frame` for diagnostics), and `StreamHandler` serves three routes: `/` (the `VIEWER_HTML` receiver page), `/stream` (the MJPEG multipart feed), and `/health` (JSON diagnostic payload merged from `FrameBuffer` state + an optional `status_provider` callable). The viewer HTML **must not** poll `/health` — that endpoint is diagnostic only. Reconnect in the viewer is driven solely by `img.onerror` (the server-side stream loop now waits indefinitely; the old client stall timer and server idle-break caused spurious disconnects and were removed).

3. **`manager.py`** — `BroadcastManager` orchestrates capture + streaming + HTTP server as one runtime. It owns the LAN URL (`get_lan_ip`), the shutdown watcher, and an IPC command listener (`handle_runtime_command`, `start_command_listener`) used by the desktop UI to drive the background broadcast.

4. **`desktop.py`** — PySide6 operator UI (`DisplayShareDesktopApp`, `launch_app`). Responsible for target selection, preview rendering, diagnostics copy/paste, and all user-facing capability summaries. The UI talks to `BroadcastManager` and the capture layer; avoid bypassing those abstractions from the UI.

5. **`cli.py`** — the legacy CLI that `launcher.py --cli` delegates to. Kept for troubleshooting; not the primary surface.

6. **`config.py`** / **`contracts.py`** — settings and shared types used across the layers.

The flow for a live broadcast: desktop UI → `BroadcastManager` → capture backend (`start_ffmpeg` → ffmpeg subprocess → reader thread) → `FrameBuffer` → `StreamHandler` HTTP server → receiver browser.

## Conventions

- Keep root-level `.py` files as thin shims. New logic goes under `ccfii_display_share/`.
- Platform-specific code belongs in `capture/backends/<platform>.py`, not sprinkled through the package.
- Tests live in `tests/` and follow `test_<subject>.py`. The three files listed in `README.md` ("Verification" section) are the canonical smoke tests to run after changes.
- When a change touches capture, streaming, or startup, also run the relevant item from the "Manual Verification Matrix" in `README.md` — it enumerates the supported platform/build combinations.
- `tests/test_startup.py` imports via the `server` compatibility shim (`import server` + `server.FrameBuffer`, `server.StreamHandler`, etc.). When adding new public symbols to `ccfii_display_share/`, re-export them through `server.py` so these tests can reach them without crossing the package boundary.

## Using Serena MCP

This project is registered with Serena (`.serena/project.yml`). Serena's symbolic tools are the preferred way to read and edit code in this repo — they avoid blowing context on full files and let you jump directly to the symbol you need.

**Before you start work on a task, check existing memories** — they are intentionally kept up to date:

- `project_overview` — purpose, tech stack, package layout
- `suggested_commands` — dev / test / packaging commands (Darwin-aware)
- `style_and_conventions` — shim-vs-package rule, platform-backend isolation
- `task_completion_checklist` — the three canonical pytest files and the verification matrix

Read these with `mcp__serena__list_memories` / `mcp__serena__read_memory` at the start of a session so you start from the current state rather than rediscovering it.

**Reading code — prefer symbolic over full-file reads.** The package is Python with clean symbol boundaries, so these flows work well:

1. `mcp__serena__get_symbols_overview` on a file (e.g. `ccfii_display_share/streaming.py` or `ccfii_display_share/capture/__init__.py`) to see its classes and top-level functions without loading the body.
2. `mcp__serena__find_symbol` with `name_path` like `BroadcastManager/start`, `FrameBuffer/update`, `StreamHandler/_serve_health`, or `CaptureController/start_capture` to pull a single symbol's body. Use `include_body=True` only when you actually need the source.
3. `mcp__serena__find_referencing_symbols` when you change a signature — essential because `server.py` and `desktop_app.py` are compatibility shims that re-export a lot, so grepping alone can under-count call sites.
4. Fall back to `mcp__serena__search_for_pattern` (or the plain `Grep` tool) only when symbol lookup isn't enough — for example tracking config constants, `VIEWER_HTML` strings, or FFmpeg CLI flags.

`Read` on a whole file is fine for small files (`config.py`, `contracts.py`, `desktop_app.py`, `server.py`, any test file), but avoid it on `capture/__init__.py` (~600 lines) and `desktop.py` — use `find_symbol` instead.

**Editing — use symbolic edits where they fit.** Replacing a method or function body is cleaner and safer with:

- `mcp__serena__replace_symbol_body` for whole-symbol rewrites (e.g. a method refactor).
- `mcp__serena__insert_after_symbol` / `mcp__serena__insert_before_symbol` to add new methods or functions in the right place.

For edits that touch a few lines inside a symbol, prefer the normal `Edit` tool — symbolic replace is overkill when you only need to flip a couple of lines.

**Never edit autogenerated / vendored content symbolically** — there isn't any in this repo today, but PyInstaller output under `build/` and `dist/` is already gitignored and must not be touched.

**When you learn something durable about the repo** (a convention, a non-obvious constraint, a gotcha you had to discover), update the matching memory with `mcp__serena__write_memory` so the next session starts ahead. Keep memories scoped and factual; do not dump conversation history into them.

**When to refresh Serena's index:** after large refactors (many files moved or renamed), call `mcp__serena__check_onboarding_performed` — if it reports stale, re-run `mcp__serena__onboarding`. Day-to-day edits do not need this.

## Global rule

Do not edit files autogenerated by Shopify. (Not currently relevant to this repo, but noted from user global instructions.)
