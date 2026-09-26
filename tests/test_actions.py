import unittest

from acf.actions import remove_dead_air_from_plan


class ActionTests(unittest.TestCase):
    def test_remove_dead_air_splits_plan(self):
        plan = {
            "edit_decisions": [
                {
                    "source": "C:/video.mp4",
                    "start": 0,
                    "end": 10,
                    "action": "keep",
                }
            ]
        }
        silence = {
            "sources": [
                {
                    "source": "C:/video.mp4",
                    "silence": [
                        {"start": 4, "end": 6, "duration": 2}
                    ],
                }
            ]
        }
        result = remove_dead_air_from_plan(plan, silence)
        decisions = result["edit_decisions"]
        self.assertEqual(len(decisions), 2)
        self.assertAlmostEqual(decisions[0]["end"], 3.88, places=2)
        self.assertAlmostEqual(decisions[1]["start"], 6.12, places=2)
