"""Tests for desktop app helper behavior."""

from pathlib import Path
import unittest

import server

from desktop_app import (
    build_preview_caption,
    build_capability_summary,
    build_diagnostics_copy_text,
    build_preflight_capability_summary,
    build_stylesheet,
    calculate_preview_size,
    calculate_logo_size,
    build_status_text,
    format_target_option,
    parse_int_setting,
)
from ccfii_display_share.contracts import CaptureBackendCapabilities


class FakeMonitor:
    x = 0
    y = 0
    width = 1920
    height = 1080
    name = "Front LED Wall"


class DesktopAppHelpersTest(unittest.TestCase):
    def test_root_desktop_module_is_compatibility_wrapper(self):
        wrapper = Path(__file__).resolve().parents[1] / "desktop_app.py"
        source = wrapper.read_text()

        self.assertIn("ccfii_display_share.desktop", source)

    def test_format_target_option_for_desktop_target(self):
        target = server.CaptureTarget.desktop(FakeMonitor())

        label = format_target_option(target)

        self.assertIn("Desktop", label)
        self.assertIn("1920x1080", label)

    def test_build_status_text_for_live_state(self):
        text = build_status_text({
            "is_running": True,
            "viewer_count": 3,
            "target_label": "Desktop: Front LED Wall - 1920x1080 at (0, 0)",
            "viewer_url": "http://192.168.1.15:8080",
        })

        self.assertIn("Broadcasting live", text)
        self.assertIn("3 device", text)
        self.assertIn("192.168.1.15:8080", text)

    def test_parse_int_setting_falls_back_when_blank(self):
        self.assertEqual(parse_int_setting("", 30, 1, 60), 30)

    def test_parse_int_setting_rejects_out_of_range_values(self):
        with self.assertRaises(ValueError):
            parse_int_setting("100", 30, 1, 60)

    def test_build_preview_caption_for_desktop_source(self):
        target = server.CaptureTarget.desktop(FakeMonitor())

        caption = build_preview_caption(target)

        self.assertIn("Front LED Wall", caption)

    def test_calculate_preview_size_preserves_aspect_ratio(self):
        width, height = calculate_preview_size(1920, 1080, 480, 320)

        self.assertEqual((width, height), (480, 270))

    def test_calculate_preview_size_returns_safe_minimum_when_box_is_tiny(self):
        width, height = calculate_preview_size(1920, 1080, 40, 40)

        self.assertGreaterEqual(width, 1)
        self.assertGreaterEqual(height, 1)

    def test_calculate_logo_size_caps_logo_inside_header(self):
        width, height = calculate_logo_size(658, 658, 1180)

        self.assertLessEqual(width, 180)
        self.assertLessEqual(height, 180)
        self.assertEqual(width, height)

    def test_stylesheet_does_not_apply_background_to_every_widget(self):
        stylesheet = build_stylesheet()

        self.assertNotIn("QWidget {\n", stylesheet)
        self.assertIn("QLabel {\n", stylesheet)
        self.assertIn("background: transparent;", stylesheet)

    def test_build_capability_summary_includes_supported_sources_and_permissions(self):
        summary = build_capability_summary(
            CaptureBackendCapabilities(
                display_capture=True,
                window_capture=False,
                preview_capture=True,
                start_capture=True,
                stop_capture=True,
                permissions_required=("Screen Recording",),
                notes=("Native preview enabled",),
            )
        )

        self.assertIn("Display capture", summary)
        self.assertIn("Window capture unavailable", summary)
        self.assertIn("Screen Recording", summary)
        self.assertIn("Native preview enabled", summary)

    def test_build_diagnostics_copy_text_includes_platform_context(self):
        text = build_diagnostics_copy_text(
            {
                "backend_name": "windows",
                "capabilities": CaptureBackendCapabilities(
                    display_capture=True,
                    window_capture=True,
                    preview_capture=True,
                    start_capture=True,
                    stop_capture=True,
                ),
                "error": "capture backend failed",
            }
        )

        self.assertIn("Backend: windows", text)
        self.assertIn("capture backend failed", text)
        self.assertIn("Display capture: enabled", text)

    def test_build_preflight_capability_summary_uses_backend_before_manager_exists(self):
        summary = build_preflight_capability_summary(
            "macos",
            CaptureBackendCapabilities(
                display_capture=False,
                window_capture=False,
                preview_capture=True,
                start_capture=False,
                stop_capture=True,
                permissions_required=("Screen Recording",),
                notes=("Preview available before broadcast support.",),
            ),
        )

        self.assertIn("Backend: macos", summary)
        self.assertIn("Screen Recording", summary)
        self.assertIn("Preview available before broadcast support.", summary)


if __name__ == "__main__":
    unittest.main()
