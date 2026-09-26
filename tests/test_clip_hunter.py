import unittest

from acf.clip_hunter import chunk_segments


class ClipHunterTests(unittest.TestCase):
    def test_chunk_segments(self):
        segments = [
            {"start": i, "end": i + 1, "text": str(i), "source": "video.mp4"}
            for i in range(250)
        ]
        chunks = chunk_segments(segments, size=100, max_chunks=3)
        self.assertEqual([len(chunk) for chunk in chunks], [100, 100, 50])
