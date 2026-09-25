import json
import unittest
from pathlib import Path
import tempfile

from acf.transcription import normalize_whisper, render_markdown, write_srt


class TranscriptTests(unittest.TestCase):
    def test_normalizes_common_whisper_shape(self):
        raw = {
            "language": "en",
            "transcription": [
                {"timestamps": {"from": "00:00:01,000", "to": "00:00:03,250"}, "text": "Hello   world !"}
            ],
        }
        data = normalize_whisper(raw, "clip.wav")
        self.assertEqual(data["language"], "en")
        self.assertEqual(data["segments"][0]["start"], 1.0)
        self.assertEqual(data["segments"][0]["end"], 3.25)
        self.assertEqual(data["segments"][0]["text"], "Hello world!")

    def test_writes_srt(self):
        data = normalize_whisper({
            "segments": [{"start": 1, "end": 3, "text": "Hello world"}]
        })
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "out.srt"
            self.assertTrue(write_srt(data, path, 0, 4))
            self.assertIn("00:00:01,000 --> 00:00:03,000", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
