"""Tests for startup and installation behavior."""

import importlib
from io import BytesIO
from pathlib import Path
import tempfile
import time
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

    def test_frame_buffer_reports_viewer_count(self):
        frame_buffer = server.FrameBuffer()

        frame_buffer.add_viewer()
        frame_buffer.add_viewer()
        frame_buffer.remove_viewer()

        self.assertEqual(frame_buffer.viewer_count, 1)

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

    def test_github_actions_workflow_builds_windows_artifacts(self):
        workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text()

        self.assertTrue(
            "windows-latest" in workflow or "blacksmith-4vcpu-windows-2025" in workflow
        )
        self.assertIn("gh release create", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("build_installer.ps1", workflow)
        self.assertIn("installer/Output/CCFIIDisplayShareInstaller.exe", workflow)
        self.assertIn("Determine next release tag", workflow)
        self.assertIn("$LASTEXITCODE = 0", workflow)

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

    def test_stream_handler_stops_stale_stream_to_allow_client_reconnect(self):
        class FakeFrameBuffer:
            def __init__(self):
                self.wait_calls = 0

            def add_viewer(self):
                pass

            def remove_viewer(self):
                pass

            def wait_for_new_frame(self, _last_version, timeout=2.0):
                self.wait_calls += 1
                return None, 0

        class FakeWriter:
            def __init__(self):
                self.chunks = []

            def write(self, data):
                self.chunks.append(data)

        handler = server.StreamHandler.__new__(server.StreamHandler)
        handler.frame_buffer = FakeFrameBuffer()
        handler.wfile = FakeWriter()
        handler.send_response = lambda _code: None
        handler.send_header = lambda _name, _value: None
        handler.end_headers = lambda: None

        handler._serve_stream()

        self.assertEqual(handler.frame_buffer.wait_calls, server.STREAM_IDLE_RETRIES)

    def test_viewer_html_retries_stream_after_disconnect(self):
        html = server.VIEWER_HTML.decode("utf-8")

        self.assertIn("setTimeout(connectStream", html)
        self.assertIn("/stream?ts=", html)
        self.assertIn("img.onerror", html)

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
        first_monitor = server.CaptureTarget.desktop(FakeMonitor())
        monitor = FakeMonitor()
        monitor.x = 100
        monitor.y = 50
        monitor.width = 1920
        monitor.height = 1080
        selected_monitor = server.CaptureTarget.desktop(monitor)
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
