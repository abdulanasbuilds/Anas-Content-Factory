import tempfile
import unittest
from pathlib import Path

from acf.state import ensure_state, recover_for_resume, save, start_stage


class StateTests(unittest.TestCase):
    def test_running_stage_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "project.json"
            save(path, ensure_state({"version": 2, "stages": {"ANALYZING": {"status": "running", "attempts": 1}}}))
            state = recover_for_resume(path)
            self.assertEqual(state["stages"]["ANALYZING"]["status"], "pending")

    def test_start_stage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "project.json"
            save(path, ensure_state({}))
            state = start_stage(path, "PLANNING")
            self.assertEqual(state["stages"]["PLANNING"]["attempts"], 1)
