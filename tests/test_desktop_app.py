"""Tests for desktop app helper behavior."""

from pathlib import Path
import unittest

import server

from desktop_app import build_status_text, format_target_option, parse_int_setting


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


if __name__ == "__main__":
    unittest.main()
