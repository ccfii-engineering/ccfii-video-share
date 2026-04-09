"""Tests for startup and installation behavior."""

import importlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
import sys
import threading
import unittest
from unittest.mock import patch

import server


ROOT = Path(__file__).resolve().parents[1]


class FakeMonitor:
    x = 10
    y = 20
    width = 1280
    height = 720
    name = "Display 1"


class FakeProcess:
    def __init__(self, stdout_data: bytes = b"", stderr_data: bytes = b""):
        self.stdout = BytesIO(stdout_data)
        self.stderr = BytesIO(stderr_data)
        self.terminated = False
        self.wait_calls = 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.wait_calls += 1
        return 0


class TestStartupBehavior(unittest.TestCase):
    def test_application_package_exports_core_runtime_symbols(self):
        package = importlib.import_module("ccfii_display_share")

        self.assertTrue(hasattr(package, "BroadcastManager"))
        self.assertTrue(hasattr(package, "CaptureTarget"))
        self.assertTrue(hasattr(package, "FrameBuffer"))

    def test_capture_contract_module_exposes_backend_interface(self):
        contracts = importlib.import_module("ccfii_display_share.contracts")

        self.assertTrue(hasattr(contracts, "CaptureBackendContract"))
        self.assertTrue(hasattr(contracts, "CaptureBackendCapabilities"))
        self.assertTrue(hasattr(contracts, "BackendError"))

    def test_capture_module_resolves_windows_backend_adapter(self):
        capture_module = importlib.import_module("ccfii_display_share.capture")

        backend = capture_module.resolve_capture_backend()

        expected_backend = "macos" if sys.platform == "darwin" else "windows"
        self.assertEqual(backend.name, expected_backend)
        self.assertTrue(hasattr(backend, "list_displays"))
        self.assertTrue(hasattr(backend, "list_windows"))

    def test_capture_backend_registry_resolves_macos_backend(self):
        registry = importlib.import_module("ccfii_display_share.capture.backends")

        backend = registry.get_backend("darwin")

        self.assertEqual(backend.name, "macos")
        self.assertTrue(hasattr(backend, "get_capabilities"))

    def test_macos_backend_reports_screen_recording_permission_requirement(self):
        macos_backend = importlib.import_module("ccfii_display_share.capture.backends.macos")

        backend = macos_backend.MacOSCaptureBackend()
        capabilities = backend.get_capabilities()

        self.assertFalse(capabilities.display_capture)
        self.assertTrue(capabilities.preview_capture)
        self.assertFalse(capabilities.start_capture)
        self.assertTrue(capabilities.stop_capture)
        self.assertFalse(capabilities.window_capture)
        self.assertIn("Screen Recording", capabilities.permissions_required)
        self.assertGreaterEqual(len(capabilities.notes), 1)

    def test_macos_backend_rejects_live_capture_until_streaming_is_implemented(self):
        macos_backend = importlib.import_module("ccfii_display_share.capture.backends.macos")

        backend = macos_backend.MacOSCaptureBackend()

        with self.assertRaises(RuntimeError) as error:
            backend.start_capture(object(), fps=30, quality=5)

        self.assertIn("not implemented", str(error.exception).lower())

    def test_macos_backend_lists_display_sources(self):
        macos_backend = importlib.import_module("ccfii_display_share.capture.backends.macos")

        class FakeMonitor:
            x = 0
            y = 0
            width = 1440
            height = 900
            name = "MacBook Pro"

        with patch("ccfii_display_share.capture.backends.macos.list_monitors", return_value=[FakeMonitor()]):
            backend = macos_backend.MacOSCaptureBackend()
            displays = backend.list_displays()

        self.assertEqual(len(displays), 1)
        self.assertIn("MacBook Pro", displays[0].label)

    def test_macos_backend_normalizes_permission_denied_preview_error(self):
        macos_backend = importlib.import_module("ccfii_display_share.capture.backends.macos")

        class FakeMonitor:
            x = 0
            y = 0
            width = 1440
            height = 900
            name = "MacBook Pro"

        with patch("ccfii_display_share.capture.backends.macos.list_monitors", return_value=[FakeMonitor()]):
            backend = macos_backend.MacOSCaptureBackend()
            source = backend.list_displays()[0]

        with patch(
            "ccfii_display_share.capture.backends.macos.ImageGrab.grab",
            side_effect=OSError("not authorized to capture screen"),
        ):
            with self.assertRaises(RuntimeError):
                backend.capture_preview(source, "/tmp/preview.png")

        error = backend.get_error()

        self.assertIsNotNone(error)
        self.assertEqual(error.code, "macos_screen_recording_permission_denied")
        self.assertIn("Screen Recording", error.message)

    def test_capture_discovery_routes_through_backend_adapter(self):
        capture_module = importlib.import_module("ccfii_display_share.capture")
        display_sentinel = object()
        window_sentinel = object()
        calls = []

        class FakeBackend:
            name = "fake"

            def list_displays(self):
                calls.append("displays")
                return [display_sentinel]

            def list_windows(self):
                calls.append("windows")
                return [window_sentinel]

        with patch(
            "ccfii_display_share.capture.resolve_capture_backend",
            return_value=FakeBackend(),
        ):
            displays = capture_module.list_monitors()
            windows = capture_module.list_windows()

        self.assertEqual(displays, [display_sentinel])
        self.assertEqual(windows, [window_sentinel])
        self.assertEqual(calls, ["displays", "windows"])

    def test_frame_buffer_reports_viewer_count(self):
        frame_buffer = server.FrameBuffer()

        frame_buffer.add_viewer()
        frame_buffer.add_viewer()
        frame_buffer.remove_viewer()

        self.assertEqual(frame_buffer.viewer_count, 1)

    def test_frame_buffer_has_no_frame_before_any_update(self):
        frame_buffer = server.FrameBuffer()

        self.assertFalse(frame_buffer.has_frame)
        self.assertIsNone(frame_buffer.last_frame_age_seconds)

    def test_frame_buffer_tracks_last_frame_age_after_update(self):
        frame_buffer = server.FrameBuffer()

        frame_buffer.update(b"\xff\xd8frame\xff\xd9")

        self.assertTrue(frame_buffer.has_frame)
        age = frame_buffer.last_frame_age_seconds
        self.assertIsNotNone(age)
        self.assertGreaterEqual(age, 0.0)
        self.assertLess(age, 1.0)

    def test_ffmpeg_reader_reports_stderr_details(self):
        proc = FakeProcess(stderr_data=b"Unknown input format: gdigrab")
        buffer = server.FrameBuffer()
        shutdown_event = threading.Event()

        with patch("builtins.print") as mock_print:
            server.ffmpeg_reader(proc, buffer, shutdown_event)

        self.assertTrue(shutdown_event.is_set())
        printed = "\n".join(
            " ".join(str(arg) for arg in call.args) for call in mock_print.call_args_list
        )
        self.assertIn("Unknown input format: gdigrab", printed)

    @patch("server.subprocess.Popen")
    def test_start_ffmpeg_captures_stderr(self, mock_popen):
        target = server.CaptureTarget.desktop(FakeMonitor())
        server.start_ffmpeg(target, fps=30, quality=5)

        self.assertEqual(mock_popen.call_args.kwargs["stderr"], server.subprocess.PIPE)

    @patch("server.subprocess.Popen")
    def test_start_ffmpeg_uses_desktop_offsets_for_display_target(self, mock_popen):
        target = server.CaptureTarget.desktop(FakeMonitor())

        server.start_ffmpeg(target, fps=30, quality=5)

        cmd = mock_popen.call_args.args[0]
        self.assertIn("-offset_x", cmd)
        self.assertIn("-offset_y", cmd)
        self.assertIn("-video_size", cmd)
        self.assertIn("desktop", cmd)

    @patch("server.subprocess.Popen")
    def test_start_ffmpeg_uses_window_title_for_window_target(self, mock_popen):
        target = server.CaptureTarget.window(12345, "Notepad")

        server.start_ffmpeg(target, fps=30, quality=5)

        cmd = mock_popen.call_args.args[0]
        self.assertIn("title=Notepad", cmd)
        self.assertNotIn("-offset_x", cmd)
        self.assertNotIn("-offset_y", cmd)
        self.assertNotIn("-video_size", cmd)

    def test_build_preview_command_uses_desktop_capture_geometry(self):
        target = server.CaptureTarget.desktop(FakeMonitor())

        cmd = server.build_preview_command(target, "/tmp/preview.png")

        self.assertIn("-offset_x", cmd)
        self.assertIn("-offset_y", cmd)
        self.assertIn("-video_size", cmd)
        self.assertIn("/tmp/preview.png", cmd)

    def test_build_preview_command_uses_window_title_for_window_preview(self):
        target = server.CaptureTarget.window(12345, "Presenter View")

        cmd = server.build_preview_command(target, "preview.png")

        self.assertIn("title=Presenter View", cmd)
        self.assertIn("preview.png", cmd)
        self.assertNotIn("-offset_x", cmd)

    def test_capture_preview_image_uses_native_desktop_grab(self):
        target = server.CaptureTarget.desktop(FakeMonitor())

        class FakeImage:
            def __init__(self):
                self.saved_paths = []

            def save(self, path):
                Path(path).write_bytes(b"preview")
                self.saved_paths.append(path)

        fake_image = FakeImage()

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "preview.png"
            with patch("ccfii_display_share.capture.ImageGrab.grab", return_value=fake_image) as mock_grab:
                result = server.capture_preview_image(target, output_path)

        self.assertEqual(result, output_path)
        self.assertEqual(mock_grab.call_args.kwargs["bbox"], (10, 20, 1290, 740))
        self.assertTrue(mock_grab.call_args.kwargs["all_screens"])

    def test_capture_controller_rejects_immediate_ffmpeg_exit(self):
        target = server.CaptureTarget(
            kind="window", label="Notepad", input_name="title=Notepad",
            hwnd=None, title="Notepad",
        )

        class ImmediateExitProcess(FakeProcess):
            def poll(self):
                return 1

        def fake_start(_monitor, _fps, _quality):
            return ImmediateExitProcess(stderr_data=b"gdigrab failed")

        controller = server.CaptureController(
            monitors=[target],
            fps=15,
            quality=4,
            frame_buffer=server.FrameBuffer(),
            shutdown_event=threading.Event(),
            start_ffmpeg_fn=fake_start,
            stop_ffmpeg_fn=lambda proc: None,
            start_reader_fn=lambda proc, frame_buffer, shutdown_event, stop_event: None,
        )

        with self.assertRaises(RuntimeError) as error:
            controller.start_capture(target)

        self.assertIn("gdigrab failed", str(error.exception))

    def test_shutdown_watcher_handles_event_with_server_instance(self):
        shutdown_event = threading.Event()

        class FakeServer:
            def __init__(self):
                self.shutdown_calls = 0

            def shutdown(self):
                self.shutdown_calls += 1

        fake_server = FakeServer()
        thread = server.start_shutdown_watcher(shutdown_event, fake_server)

        shutdown_event.set()
        thread.join(timeout=1)

        self.assertEqual(fake_server.shutdown_calls, 1)

    def test_server_module_is_compatibility_wrapper(self):
        server_wrapper = (ROOT / "server.py").read_text()

        self.assertIn("from ccfii_display_share import", server_wrapper)
        self.assertIn("cli_main", server_wrapper)

    def test_requirements_include_pyside6_for_desktop_ui(self):
        requirements = (ROOT / "requirements.txt").read_text().lower()

        self.assertIn("pyside6", requirements)

    def test_run_script_launches_desktop_entrypoint(self):
        run_script = (ROOT / "run.bat").read_text()

        self.assertIn("run.pyw", run_script)

    def test_launcher_defaults_to_desktop_mode(self):
        launcher_script = (ROOT / "launcher.py").read_text()

        self.assertIn("ccfii_display_share.launcher", launcher_script)
        self.assertIn("main", launcher_script)

    def test_pyinstaller_spec_references_desktop_app_and_logo(self):
        spec_file = (ROOT / "CCFIIDisplayShare.spec").read_text()

        self.assertIn("desktop_app.py", spec_file)
        self.assertIn("assets/ccfii-logo.png", spec_file)
        self.assertIn("PySide6", spec_file)
        self.assertNotIn('collect_submodules("PySide6")', spec_file)
        self.assertIn("excludes", spec_file)

    def test_inno_setup_script_uses_ccfii_branding(self):
        setup_script = (ROOT / "installer" / "CCFIIDisplayShare.iss").read_text()

        self.assertIn("CCFII Display Share", setup_script)
        self.assertIn("CCFIIDisplayShare.exe", setup_script)

    def test_github_actions_workflow_builds_cross_platform_release(self):
        workflow = (ROOT / ".github" / "workflows" / "release-desktop-apps.yml").read_text()

        self.assertIn("name: Release Desktop Apps", workflow)
        self.assertTrue(
            "windows-latest" in workflow or "blacksmith-4vcpu-windows-2025" in workflow
        )
        self.assertIn("build-macos", workflow)
        self.assertIn("prepare-release", workflow)
        self.assertIn("publish-release", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("gh release upload", workflow)
        self.assertIn("gh release edit", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("build_installer.ps1", workflow)
        self.assertIn("installer/Output/CCFIIDisplayShareInstaller.exe", workflow)
        self.assertIn("Determine next release tag", workflow)
        self.assertIn("Create draft GitHub release", workflow)
        self.assertIn("CCFIIDisplayShare-macos.zip", workflow)
        self.assertIn("GH_REPO: ${{ github.repository }}", workflow)
        self.assertIn("iconutil", workflow)
        self.assertIn("ccfii-logo.icns", workflow)
        self.assertIn("codesign --force --deep --sign -", workflow)
        self.assertNotIn("actions/upload-artifact", workflow)

    def test_readme_mentions_unsigned_macos_app_opening_and_icon_packaging(self):
        readme = (ROOT / "README.md").read_text()

        self.assertIn(".icns", readme)
        self.assertIn("Right-click", readme)
        self.assertIn("developer cannot be verified", readme)

    def test_no_separate_macos_release_workflow_exists(self):
        workflow_path = ROOT / ".github" / "workflows" / "build-macos.yml"

        self.assertFalse(workflow_path.exists())

    def test_build_batch_script_wraps_powershell_installer_build(self):
        build_script = (ROOT / "build.bat").read_text()

        self.assertIn("build_installer.ps1", build_script)
        self.assertIn("powershell", build_script.lower())

    def test_build_script_installs_packaging_dependencies_and_generates_ico(self):
        build_script = (ROOT / "build_installer.ps1").read_text()

        self.assertIn("pillow", build_script.lower())
        self.assertIn("JRSoftware.InnoSetup", build_script)
        self.assertIn("img.save", build_script)
        self.assertIn("ffmpeg", build_script.lower())

    def test_readme_documents_windows_and_macos_packaging_requirements(self):
        readme = (ROOT / "README.md").read_text()

        self.assertIn("Windows Packaging", readme)
        self.assertIn("macOS Packaging", readme)
        self.assertIn("Screen Recording", readme)
        self.assertIn("macOS", readme)

    def test_readme_documents_manual_verification_matrix(self):
        readme = (ROOT / "README.md").read_text()
        roadmap = (ROOT / "docs" / "plans" / "2026-04-05-windows-macos-platform-roadmap.md").read_text()

        self.assertIn("Manual Verification Matrix", readme)
        self.assertIn("Windows display capture", readme)
        self.assertIn("macOS Screen Recording permission onboarding", readme)
        self.assertIn("manual verification matrix", roadmap.lower())

    def test_ffmpeg_binary_resolution_checks_packaged_location_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            packaged_path = Path(temp_dir) / "ffmpeg.exe"
            packaged_path.write_bytes(b"fake")
            command = server.resolve_ffmpeg_command(
                packaged_path=packaged_path,
                path_lookup=lambda _name: None,
            )

            self.assertEqual(command, str(packaged_path))

    def test_stream_handler_ignores_connection_aborted_on_disconnect(self):
        frame_buffer = server.FrameBuffer()
        frame_buffer.update(b"\xff\xd8frame\xff\xd9")

        class FakeWriter:
            def write(self, _data):
                raise ConnectionAbortedError("listener closed")

        handler = server.StreamHandler.__new__(server.StreamHandler)
        handler.frame_buffer = frame_buffer
        handler.wfile = FakeWriter()
        handler.send_response = lambda _code: None
        handler.send_header = lambda _name, _value: None
        handler.end_headers = lambda: None

        handler._serve_stream()

    def test_stream_handler_keeps_viewer_connected_through_capture_stall(self):
        """A transient capture stall must not close the viewer's HTTP stream.

        The server used to break out of the streaming loop after a handful of
        idle timeouts, which caused the browser viewer to flash
        "Disconnected. Reconnecting..." every time the capture pipeline went
        briefly quiet (FFmpeg pipe hiccup, blocked PrintWindow snapshot, etc.)
        even though the broadcast was still healthy. The streaming loop must
        keep waiting until the client actually disconnects or the server shuts
        down.
        """

        frame_bytes = b"\xff\xd8frame\xff\xd9"

        class FakeFrameBuffer:
            def __init__(self):
                self.wait_calls = 0
                self.viewer_added = False
                self.viewer_removed = False

            def add_viewer(self):
                self.viewer_added = True

            def remove_viewer(self):
                self.viewer_removed = True

            def wait_for_new_frame(self, last_version, timeout=2.0):
                self.wait_calls += 1
                # Simulate a long capture stall — many more idle timeouts than
                # the old guard allowed — followed by a fresh frame. Once the
                # fresh frame is delivered, raise to end the loop so the test
                # can assert what happened.
                stall_budget = 10  # >> the historical STREAM_IDLE_RETRIES = 3
                if self.wait_calls <= stall_budget:
                    return None, last_version
                return frame_bytes, last_version + 1

        class FakeWriter:
            def __init__(self):
                self.chunks = []
                self.raise_after_first_frame = False
                self.frame_written = False

            def write(self, data):
                self.chunks.append(data)
                if data == frame_bytes:
                    self.frame_written = True
                    # Simulate the client disconnecting right after the first
                    # real frame lands, so the loop terminates cleanly.
                    raise ConnectionResetError("viewer closed")

        handler = server.StreamHandler.__new__(server.StreamHandler)
        handler.frame_buffer = FakeFrameBuffer()
        handler.wfile = FakeWriter()
        handler.send_response = lambda _code: None
        handler.send_header = lambda _name, _value: None
        handler.end_headers = lambda: None

        handler._serve_stream()

        # The loop should have survived well past the old idle-retry limit and
        # still delivered the eventual frame, proving that a transient stall
        # does not terminate the viewer connection.
        self.assertGreater(
            handler.frame_buffer.wait_calls, server.STREAM_IDLE_RETRIES + 5
        )
        self.assertTrue(handler.wfile.frame_written)
        self.assertTrue(handler.frame_buffer.viewer_added)
        self.assertTrue(handler.frame_buffer.viewer_removed)

    def test_viewer_html_retries_stream_after_disconnect(self):
        html = server.VIEWER_HTML.decode("utf-8")

        self.assertIn("setTimeout(connectStream", html)
        self.assertIn("/stream?ts=", html)
        self.assertIn("img.onerror", html)

    def _build_health_handler(self, frame_buffer=None, status_provider=None):
        """Return a StreamHandler wired up for in-process /health tests."""

        class RecordingWriter:
            def __init__(self):
                self.chunks = []

            def write(self, data):
                self.chunks.append(data)

        handler = server.StreamHandler.__new__(server.StreamHandler)
        handler.frame_buffer = frame_buffer or server.FrameBuffer()
        handler.wfile = RecordingWriter()
        handler.sent_response = []
        handler.sent_headers = []
        handler.send_response = lambda code: handler.sent_response.append(code)
        handler.send_header = lambda name, value: handler.sent_headers.append((name, value))
        handler.end_headers = lambda: None
        # Reset the class attribute before each test so state does not leak.
        server.StreamHandler.status_provider = status_provider
        return handler

    def _read_health_body(self, handler) -> dict:
        body = b"".join(handler.wfile.chunks)
        return json.loads(body.decode("utf-8"))

    def test_health_endpoint_reports_no_frame_before_capture_starts(self):
        handler = self._build_health_handler()

        try:
            handler._serve_health()
        finally:
            server.StreamHandler.status_provider = None

        self.assertEqual(handler.sent_response, [200])
        content_types = [value for name, value in handler.sent_headers if name == "Content-Type"]
        self.assertEqual(content_types, ["application/json"])

        payload = self._read_health_body(handler)
        self.assertTrue(payload["alive"])
        self.assertFalse(payload["has_frame"])
        self.assertIsNone(payload["last_frame_age_ms"])
        self.assertEqual(payload["viewer_count"], 0)

    def test_health_endpoint_reports_frame_age_and_viewer_count(self):
        frame_buffer = server.FrameBuffer()
        frame_buffer.update(b"\xff\xd8frame\xff\xd9")
        frame_buffer.add_viewer()
        frame_buffer.add_viewer()

        handler = self._build_health_handler(frame_buffer=frame_buffer)

        try:
            handler._serve_health()
        finally:
            server.StreamHandler.status_provider = None

        payload = self._read_health_body(handler)
        self.assertTrue(payload["has_frame"])
        self.assertIsNotNone(payload["last_frame_age_ms"])
        self.assertGreaterEqual(payload["last_frame_age_ms"], 0)
        self.assertLess(payload["last_frame_age_ms"], 5000)
        self.assertEqual(payload["viewer_count"], 2)

    def test_health_endpoint_merges_status_provider_fields(self):
        def fake_status():
            return {
                "is_running": True,
                "target_label": "Desktop: Display 1",
                "fps": 30,
                "quality": 5,
                "backend_name": "windows",
                "error": "",
                "viewer_url": "http://192.168.1.77:9090",
                "capabilities": object(),  # must not break JSON serialization
            }

        handler = self._build_health_handler(status_provider=fake_status)

        try:
            handler._serve_health()
        finally:
            server.StreamHandler.status_provider = None

        payload = self._read_health_body(handler)
        self.assertTrue(payload["alive"])
        self.assertEqual(payload["target_label"], "Desktop: Display 1")
        self.assertEqual(payload["fps"], 30)
        self.assertEqual(payload["quality"], 5)
        self.assertEqual(payload["backend_name"], "windows")
        # Non-serializable fields (e.g. capabilities) must not leak into payload.
        self.assertNotIn("capabilities", payload)

    def test_health_endpoint_reflects_is_running_false_from_status_provider(self):
        handler = self._build_health_handler(
            status_provider=lambda: {"is_running": False, "error": "capture exited"}
        )

        try:
            handler._serve_health()
        finally:
            server.StreamHandler.status_provider = None

        payload = self._read_health_body(handler)
        self.assertFalse(payload["alive"])
        self.assertEqual(payload["error"], "capture exited")

    def test_health_endpoint_survives_failing_status_provider(self):
        def boom():
            raise RuntimeError("status provider exploded")

        handler = self._build_health_handler(status_provider=boom)

        try:
            handler._serve_health()
        finally:
            server.StreamHandler.status_provider = None

        self.assertEqual(handler.sent_response, [200])
        payload = self._read_health_body(handler)
        self.assertIn("status_error", payload)
        self.assertIn("status provider exploded", payload["status_error"])
        # Core buffer fields must still be present even when the provider fails.
        self.assertIn("viewer_count", payload)
        self.assertIn("has_frame", payload)

    def test_do_get_routes_health_requests(self):
        called = []

        handler = server.StreamHandler.__new__(server.StreamHandler)
        handler.path = "/health"
        handler._serve_viewer = lambda: called.append("viewer")
        handler._serve_stream = lambda: called.append("stream")
        handler._serve_health = lambda: called.append("health")
        handler.send_error = lambda code: called.append(f"error:{code}")

        handler.do_GET()

        self.assertEqual(called, ["health"])

    def test_viewer_html_does_not_poll_health_endpoint(self):
        """/health is diagnostic only. The viewer must not poll it — that
        would be the same class of heuristic reconnect trigger we removed
        when we killed the client-side stall timer."""

        html = server.VIEWER_HTML.decode("utf-8")

        self.assertNotIn("/health", html)

    def test_broadcast_manager_wires_health_status_provider(self):
        selected_target = server.CaptureTarget.desktop(FakeMonitor())

        class FakeController:
            def __init__(self, **kwargs):
                self.current_monitor = None

            def start_capture(self, target):
                self.current_monitor = target

            def stop_capture(self):
                pass

        class FakeServer:
            def __init__(self, address, handler_cls):
                self.address = address
                self.handler_cls = handler_cls

            def serve_forever(self):
                return None

            def shutdown(self):
                return None

        class FakeHandler:
            pass

        manager = server.BroadcastManager(
            targets=[selected_target],
            port=9090,
            fps=25,
            quality=6,
            handler_class=FakeHandler,
            lan_ip_fn=lambda: "192.168.1.77",
            controller_factory=lambda **kwargs: FakeController(**kwargs),
            server_factory=lambda address, handler_cls: FakeServer(address, handler_cls),
            shutdown_watcher_fn=lambda shutdown_event, http_server: None,
        )

        manager.start(selected_target)
        try:
            self.assertTrue(hasattr(FakeHandler, "status_provider"))
            # Bound methods are created fresh on each attribute access, so
            # identity comparison fails; compare equality (same __self__ and
            # __func__) and also verify the provider actually returns the
            # manager's status.
            self.assertEqual(FakeHandler.status_provider, manager.get_status)
            provided = FakeHandler.status_provider()
            self.assertEqual(provided["target_label"], selected_target.label)
            self.assertEqual(provided["viewer_url"], "http://192.168.1.77:9090")
            self.assertIs(FakeHandler.frame_buffer, manager.frame_buffer)
        finally:
            manager.stop()

    def test_viewer_html_has_no_client_side_stall_timer(self):
        """Mobile browsers (notably iOS Safari) do not reliably fire
        img.onload for each part of a multipart/x-mixed-replace stream, so a
        client-side stall timer that depends on onload causes spurious
        "Disconnected. Reconnecting..." flashes on phones even when the
        server is streaming fine. The server now keeps connections open
        until a real socket error, so the stall heuristic must not exist.
        Only img.onerror (real transport failure) may trigger reconnect.
        """

        html = server.VIEWER_HTML.decode("utf-8")

        self.assertNotIn("STALL_TIMEOUT", html)
        self.assertNotIn("stallTimer", html)
        self.assertNotIn("resetStallTimer", html)

    def test_do_get_routes_stream_requests_with_query_string(self):
        called = []

        handler = server.StreamHandler.__new__(server.StreamHandler)
        handler.path = "/stream?ts=123"
        handler._serve_viewer = lambda: called.append("viewer")
        handler._serve_stream = lambda: called.append("stream")
        handler.send_error = lambda code: called.append(f"error:{code}")

        handler.do_GET()

        self.assertEqual(called, ["stream"])

    def test_handle_command_switches_display_on_d(self):
        switch_calls = []

        class FakeController:
            def switch_monitor(self):
                switch_calls.append("switched")

        shutdown_event = threading.Event()

        handled = server.handle_runtime_command("d", FakeController(), shutdown_event)

        self.assertTrue(handled)
        self.assertEqual(switch_calls, ["switched"])
        self.assertFalse(shutdown_event.is_set())

    def test_handle_command_sets_shutdown_on_q(self):
        shutdown_event = threading.Event()

        handled = server.handle_runtime_command("q", object(), shutdown_event)

        self.assertTrue(handled)
        self.assertTrue(shutdown_event.is_set())

    def test_capture_controller_switches_to_selected_monitor(self):
        first_monitor = server.CaptureTarget(
            kind="window", label="Presenter", input_name="title=Presenter",
            hwnd=None, title="Presenter",
        )
        selected_monitor = server.CaptureTarget(
            kind="window", label="Lyrics", input_name="title=Lyrics",
            hwnd=None, title="Lyrics",
        )
        started_monitors = []
        stop_calls = []

        def fake_start(monitor, fps, quality):
            started_monitors.append((monitor, fps, quality))
            return FakeProcess()

        def fake_stop(proc):
            stop_calls.append(proc)

        with patch("ccfii_display_share.capture.choose_capture_target", return_value=selected_monitor):
            controller = server.CaptureController(
                monitors=[first_monitor, selected_monitor],
                fps=15,
                quality=4,
                frame_buffer=server.FrameBuffer(),
                shutdown_event=threading.Event(),
                start_ffmpeg_fn=fake_start,
                stop_ffmpeg_fn=fake_stop,
                start_reader_fn=lambda proc, frame_buffer, shutdown_event, stop_event: None,
            )

            initial_proc = controller.start_capture(controller.monitors[0])
            self.assertIsInstance(initial_proc, FakeProcess)

            controller.switch_monitor()

        self.assertEqual(started_monitors, [
            (first_monitor, 15, 4),
            (selected_monitor, 15, 4),
        ])
        self.assertEqual(stop_calls, [initial_proc])

    def test_broadcast_manager_starts_server_and_exposes_status(self):
        selected_target = server.CaptureTarget.desktop(FakeMonitor())
        capture_starts = []
        capture_stops = []

        class FakeController:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.current_monitor = None

            def start_capture(self, target):
                capture_starts.append(target)
                self.current_monitor = target

            def stop_capture(self):
                capture_stops.append(self.current_monitor)

        class FakeServer:
            def __init__(self, address, handler_cls):
                self.address = address
                self.handler_cls = handler_cls
                self.serve_forever_calls = 0
                self.shutdown_calls = 0
                self.shutdown_event = threading.Event()

            def serve_forever(self):
                self.serve_forever_calls += 1
                self.shutdown_event.wait(timeout=1)

            def shutdown(self):
                self.shutdown_calls += 1
                self.shutdown_event.set()

        manager = server.BroadcastManager(
            targets=[selected_target],
            port=9090,
            fps=25,
            quality=6,
            lan_ip_fn=lambda: "192.168.1.77",
            controller_factory=lambda **kwargs: FakeController(**kwargs),
            server_factory=lambda address, handler_cls: FakeServer(address, handler_cls),
            shutdown_watcher_fn=lambda shutdown_event, http_server: None,
        )

        manager.start(selected_target)
        time.sleep(0.01)

        status = manager.get_status()

        self.assertEqual(capture_starts, [selected_target])
        self.assertTrue(status["is_running"])
        self.assertEqual(status["viewer_url"], "http://192.168.1.77:9090")
        self.assertEqual(status["target_label"], selected_target.label)

        manager.stop()

        self.assertEqual(capture_stops, [selected_target])

    def test_broadcast_manager_exposes_backend_capabilities(self):
        selected_target = server.CaptureTarget.desktop(FakeMonitor())

        class FakeController:
            def __init__(self, **kwargs):
                self.current_monitor = None

            def start_capture(self, target):
                self.current_monitor = target

            def stop_capture(self):
                pass

        class FakeBackend:
            def get_capabilities(self):
                return server.CaptureBackendCapabilities(
                    display_capture=True,
                    window_capture=False,
                    preview_capture=True,
                    start_capture=True,
                    stop_capture=True,
                    permissions_required=("Screen Recording",),
                    notes=("Native preview enabled",),
                )

        manager = server.BroadcastManager(
            targets=[selected_target],
            port=9090,
            fps=25,
            quality=6,
            lan_ip_fn=lambda: "192.168.1.77",
            controller_factory=lambda **kwargs: FakeController(**kwargs),
            server_factory=lambda address, handler_cls: None,
            shutdown_watcher_fn=lambda shutdown_event, http_server: None,
        )
        manager.backend = FakeBackend()

        capabilities = manager.get_status()["capabilities"]

        self.assertTrue(capabilities.display_capture)
        self.assertFalse(capabilities.window_capture)
        self.assertIn("Screen Recording", capabilities.permissions_required)

    def test_broadcast_manager_aborts_start_when_capture_backend_fails(self):
        selected_target = server.CaptureTarget.desktop(FakeMonitor())
        capture_starts = []
        server_starts = []

        class FakeController:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.current_monitor = None

            def start_capture(self, target):
                capture_starts.append(target)
                self.current_monitor = target
                setattr(self.kwargs["shutdown_event"], "ffmpeg_error", "capture backend failed")
                self.kwargs["shutdown_event"].set()

            def stop_capture(self):
                pass

        class FakeServer:
            def __init__(self, address, handler_cls):
                server_starts.append((address, handler_cls))

            def serve_forever(self):
                raise AssertionError("server should not start when capture fails")

            def shutdown(self):
                pass

        manager = server.BroadcastManager(
            targets=[selected_target],
            port=9090,
            fps=25,
            quality=6,
            lan_ip_fn=lambda: "192.168.1.77",
            controller_factory=lambda **kwargs: FakeController(**kwargs),
            server_factory=lambda address, handler_cls: FakeServer(address, handler_cls),
            shutdown_watcher_fn=lambda shutdown_event, http_server: None,
        )

        with self.assertRaises(RuntimeError) as error:
            manager.start(selected_target)

        self.assertIn("capture backend failed", str(error.exception))
        self.assertEqual(capture_starts, [selected_target])
        self.assertEqual(server_starts, [])

    def test_broadcast_manager_switch_target_restarts_capture(self):
        first_target = server.CaptureTarget.desktop(FakeMonitor())
        second_monitor = FakeMonitor()
        second_monitor.name = "Display 2"
        second_monitor.x = 100
        second_monitor.y = 200
        second_monitor.width = 1920
        second_monitor.height = 1080
        second_target = server.CaptureTarget.desktop(second_monitor)
        events = []

        class FakeController:
            def __init__(self, **kwargs):
                self.current_monitor = None

            def start_capture(self, target):
                events.append(("start", target.label))
                self.current_monitor = target

            def stop_capture(self):
                events.append(("stop", self.current_monitor.label))

        class FakeServer:
            def __init__(self, address, handler_cls):
                self.address = address

            def serve_forever(self):
                return None

            def shutdown(self):
                return None

        manager = server.BroadcastManager(
            targets=[first_target, second_target],
            port=8080,
            fps=30,
            quality=5,
            lan_ip_fn=lambda: "10.0.0.10",
            controller_factory=lambda **kwargs: FakeController(**kwargs),
            server_factory=lambda address, handler_cls: FakeServer(address, handler_cls),
            shutdown_watcher_fn=lambda shutdown_event, http_server: None,
        )

        manager.start(first_target)
        manager.switch_target(second_target)

        self.assertEqual(events, [
            ("start", first_target.label),
            ("stop", first_target.label),
            ("start", second_target.label),
        ])
        self.assertEqual(manager.get_status()["target_label"], second_target.label)


if __name__ == "__main__":
    unittest.main()
