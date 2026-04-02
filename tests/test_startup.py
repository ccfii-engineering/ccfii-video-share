"""Tests for startup and installation behavior."""

from io import BytesIO
from pathlib import Path
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
        server.start_ffmpeg(FakeMonitor(), fps=30, quality=5)

        self.assertEqual(mock_popen.call_args.kwargs["stderr"], server.subprocess.PIPE)

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

    def test_install_script_uses_python_module_pip(self):
        install_script = (ROOT / "install.bat").read_text()

        self.assertIn("python -m pip install -r requirements.txt", install_script)

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

    def test_viewer_html_retries_stream_after_disconnect(self):
        html = server.VIEWER_HTML.decode("utf-8")

        self.assertIn("setTimeout(connectStream", html)
        self.assertIn("/stream?ts=", html)
        self.assertIn("img.onerror", html)

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
        first_monitor = FakeMonitor()
        selected_monitor = FakeMonitor()
        selected_monitor.x = 100
        selected_monitor.y = 50
        selected_monitor.width = 1920
        selected_monitor.height = 1080
        started_monitors = []
        stop_calls = []

        def fake_start(monitor, fps, quality):
            started_monitors.append((monitor, fps, quality))
            return FakeProcess()

        def fake_stop(proc):
            stop_calls.append(proc)

        with patch("server.choose_monitor", return_value=selected_monitor):
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
            (controller.monitors[0], 15, 4),
            (selected_monitor, 15, 4),
        ])
        self.assertEqual(stop_calls, [initial_proc])


if __name__ == "__main__":
    unittest.main()
