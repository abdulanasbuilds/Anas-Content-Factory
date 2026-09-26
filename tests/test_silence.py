import unittest

from acf.silence import parse_silencedetect


class SilenceTests(unittest.TestCase):
    def test_parse_silence_ranges(self):
        stderr = """
[silencedetect @ 0x1] silence_start: 4.500
[silencedetect @ 0x1] silence_end: 6.100 | silence_duration: 1.600
[silencedetect @ 0x1] silence_start: 10.000
[silencedetect @ 0x1] silence_end: 11.250 | silence_duration: 1.250
"""
        result = parse_silencedetect(stderr)
        self.assertEqual(result[0]["start"], 4.5)
        self.assertEqual(result[0]["end"], 6.1)
        self.assertEqual(result[0]["duration"], 1.6)
        self.assertEqual(len(result), 2)
