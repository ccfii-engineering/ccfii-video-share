"""Tests for MJPEG frame extraction from raw byte stream."""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from server import extract_frames


class TestExtractFrames(unittest.TestCase):
    SOI = b"\xff\xd8"
    EOI = b"\xff\xd9"

    def _make_frame(self, payload: bytes = b"JPEG_DATA") -> bytes:
        return self.SOI + payload + self.EOI

    def test_single_complete_frame(self):
        frame = self._make_frame()
        frames, remaining = extract_frames(frame)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0], frame)
        self.assertEqual(remaining, b"")

    def test_two_frames_back_to_back(self):
        f1 = self._make_frame(b"AAA")
        f2 = self._make_frame(b"BBB")
        frames, remaining = extract_frames(f1 + f2)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0], f1)
        self.assertEqual(frames[1], f2)

    def test_incomplete_frame_kept_in_remaining(self):
        complete = self._make_frame(b"DONE")
        partial = self.SOI + b"PARTIAL"
        frames, remaining = extract_frames(complete + partial)
        self.assertEqual(len(frames), 1)
        self.assertEqual(remaining, partial)

    def test_empty_input(self):
        frames, remaining = extract_frames(b"")
        self.assertEqual(frames, [])
        self.assertEqual(remaining, b"")

    def test_garbage_before_first_soi(self):
        garbage = b"\x00\x01\x02"
        frame = self._make_frame()
        frames, remaining = extract_frames(garbage + frame)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0], frame)

    def test_no_complete_frame(self):
        partial = self.SOI + b"WAITING"
        frames, remaining = extract_frames(partial)
        self.assertEqual(frames, [])
        self.assertEqual(remaining, partial)

    def test_trailing_ff_preserved(self):
        """A trailing 0xFF could be half of a SOI split across chunks."""
        data = b"\x00\x01\xff"
        frames, remaining = extract_frames(data)
        self.assertEqual(frames, [])
        self.assertEqual(remaining, b"\xff")


if __name__ == "__main__":
    unittest.main()
