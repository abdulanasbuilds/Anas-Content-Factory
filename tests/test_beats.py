import tempfile
import unittest
from pathlib import Path

from acf.beats import normalize_beats


class BeatTests(unittest.TestCase):
    def test_normalize_beats(self):
        def resolve_source(value, manifest, input_path):
            return Path("video.mp4")

        with tempfile.TemporaryDirectory() as folder:
            beats = normalize_beats(
                {
                    "motion_beats": [
                        {"source": "video.mp4", "start": 1, "end": 3, "text": "Hello"},
                        {"source": "video.mp4", "start": 0, "end": 1, "text": ""},
                    ]
                },
                resolve_source,
                {"files": []},
                Path(folder),
                beat_limit=4,
            )
            self.assertEqual(len(beats), 1)
            self.assertEqual(beats[0]["text"], "Hello")
