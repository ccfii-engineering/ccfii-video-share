"""Broadcast orchestration and runtime control."""

from __future__ import annotations

import socket
import threading
from http.server import ThreadingHTTPServer

from .capture import CaptureController, CaptureTarget, resolve_capture_backend
from .streaming import FrameBuffer, StreamHandler


def get_lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


def start_shutdown_watcher(shutdown_event: threading.Event,
                           server: ThreadingHTTPServer) -> threading.Thread:
    def watch_shutdown():
        shutdown_event.wait()
        print("[!] Initiating shutdown due to FFmpeg exit...")
        server.shutdown()

    thread = threading.Thread(target=watch_shutdown, daemon=True)
    thread.start()
    return thread


class BroadcastManager:
    """Programmatic lifecycle manager for display sharing."""

    def __init__(self, targets, port: int, fps: int, quality: int,
                 handler_class=StreamHandler,
                 controller_factory=CaptureController,
                 server_factory=ThreadingHTTPServer,
                 shutdown_watcher_fn=start_shutdown_watcher,
                 lan_ip_fn=None):
        self.targets = targets
        self.port = port
        self.fps = fps
        self.quality = quality
        self.handler_class = handler_class
        self.controller_factory = controller_factory
        self.server_factory = server_factory
        self.shutdown_watcher_fn = shutdown_watcher_fn
        self.lan_ip_fn = lan_ip_fn or get_lan_ip
        self.frame_buffer = FrameBuffer()
        self.shutdown_event = threading.Event()
        self.controller = controller_factory(
            monitors=targets,
            fps=fps,
            quality=quality,
            frame_buffer=self.frame_buffer,
            shutdown_event=self.shutdown_event,
        )
        self.backend = resolve_capture_backend()
        self.server = None
        self._server_thread = None
        self._watcher_thread = None
        self._is_running = False
        self._lock = threading.Lock()

    def start(self, target: CaptureTarget):
        with self._lock:
            if self._is_running:
                return
            self.shutdown_event.clear()
            self.controller.start_capture(target)
            if self.shutdown_event.wait(timeout=0.05):
                self.controller.stop_capture()
                raise RuntimeError(
                    getattr(self.shutdown_event, "ffmpeg_error", "")
                    or "Capture backend failed to start."
                )
            self.handler_class.frame_buffer = self.frame_buffer
            self.server = self.server_factory(("0.0.0.0", self.port),
                                              self.handler_class)
            self._watcher_thread = self.shutdown_watcher_fn(
                self.shutdown_event, self.server)
            self._server_thread = threading.Thread(
                target=self.server.serve_forever,
                daemon=True,
            )
            self._server_thread.start()
            self._is_running = True

    def stop(self):
        with self._lock:
            if not self._is_running:
                return
            self.shutdown_event.set()
            self.controller.stop_capture()
            if self.server is not None:
                self.server.shutdown()
            server_thread = self._server_thread
            self._server_thread = None
            self.server = None
            self._is_running = False
        if server_thread is not None and server_thread.is_alive():
            server_thread.join(timeout=5)

    def is_healthy(self) -> bool:
        server_thread = self._server_thread
        server_alive = server_thread is not None and server_thread.is_alive()
        return self._is_running and not self.shutdown_event.is_set() and server_alive

    def switch_target(self, target: CaptureTarget):
        if not self._is_running:
            self.start(target)
            return
        self.controller.stop_capture()
        self.controller.start_capture(target)

    def get_status(self) -> dict[str, object]:
        current_target = self.controller.current_monitor
        ffmpeg_error = getattr(self.shutdown_event, "ffmpeg_error", "") or ""
        is_running = self.is_healthy()
        capabilities = self.backend.get_capabilities() if self.backend is not None else None
        return {
            "is_running": is_running,
            "backend_running": self._is_running,
            "viewer_count": self.frame_buffer.viewer_count,
            "viewer_url": f"http://{self.lan_ip_fn()}:{self.port}",
            "target_label": current_target.label if current_target else "",
            "fps": self.fps,
            "quality": self.quality,
            "error": ffmpeg_error,
            "backend_name": getattr(self.backend, "name", ""),
            "capabilities": capabilities,
        }


def handle_runtime_command(command: str, controller: CaptureController,
                           shutdown_event: threading.Event) -> bool:
    normalized = command.strip().lower()
    if normalized in {"d", "display", "screen"}:
        controller.switch_monitor()
        return True
    if normalized in {"q", "quit", "exit"}:
        print("[*] Shutting down...")
        shutdown_event.set()
        return True
    if normalized in {"h", "help", "?"}:
        print("Commands: d = switch display/window, q = quit, h = help")
        return True
    return False


def start_command_listener(controller: CaptureController,
                           shutdown_event: threading.Event) -> threading.Thread:
    def command_loop():
        print("Commands: d = switch display/window, q = quit, h = help")
        while not shutdown_event.is_set():
            try:
                command = input("> ")
            except EOFError:
                return
            if not handle_runtime_command(command, controller, shutdown_event):
                print("Unknown command. Type 'h' for help.")

    thread = threading.Thread(target=command_loop, daemon=True)
    thread.start()
    return thread
