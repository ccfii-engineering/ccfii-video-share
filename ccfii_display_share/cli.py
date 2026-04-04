"""CLI entry point for the legacy console workflow."""

from __future__ import annotations

import argparse
import sys
from http.server import ThreadingHTTPServer

from .capture import build_capture_targets, choose_capture_target, list_monitors, list_windows
from .manager import BroadcastManager, get_lan_ip, start_command_listener, start_shutdown_watcher
from .streaming import StreamHandler


def main():
    parser = argparse.ArgumentParser(
        description="Share a display over the local network.")
    parser.add_argument("--port", type=int, default=8080,
                        help="HTTP server port (default: 8080)")
    parser.add_argument("--fps", type=int, default=30,
                        help="Capture framerate (default: 30)")
    parser.add_argument("--quality", type=int, default=5,
                        help="JPEG quality 1-31, lower=better (default: 5)")
    args = parser.parse_args()

    monitors = list_monitors()
    if not monitors:
        print("No displays found.")
        sys.exit(1)
    targets = build_capture_targets(monitors, list_windows())

    manager = BroadcastManager(
        targets=targets,
        port=args.port,
        fps=args.fps,
        quality=args.quality,
        handler_class=StreamHandler,
        server_factory=ThreadingHTTPServer,
        shutdown_watcher_fn=start_shutdown_watcher,
        lan_ip_fn=get_lan_ip,
    )

    target = choose_capture_target(targets)
    manager.start(target)
    start_command_listener(manager.controller, manager.shutdown_event)

    lan_ip = get_lan_ip()
    print(f"Stream live at http://{lan_ip}:{args.port}")
    print("Press Ctrl+C to stop.\n")

    try:
        if manager.server is not None:
            manager._server_thread.join()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        manager.stop()
