import unittest
from pathlib import Path

from acf.editor import EditPlanError, validate_plan


class EditorPlanTests(unittest.TestCase):
    def test_missing_source(self):
        with self.assertRaises(EditPlanError):
            validate_plan(
                {"edit_decisions": [{"start": 0, "end": 2}]},
                {"files": []},
                Path("project"),
            )
