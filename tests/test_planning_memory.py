"""Planning accepts saved memory in both formats (found in UI4 live testing)."""

import unittest

from src.agents import planning
from src.schemas import PersistentWeakness


class TestMemoryFormats(unittest.TestCase):
    def test_weakness_names_accepts_strings_dicts_and_models(self):
        records = [
            "Docker",
            {"skill": "SQL", "last_score": 1, "notes": "Skipped in the last session."},
            PersistentWeakness(skill="Git", last_score=2, notes="Explain branching."),
        ]
        self.assertEqual(planning._weakness_names(records), ["Docker", "SQL", "Git"])

    def test_bad_entries_are_ignored(self):
        self.assertEqual(planning._weakness_names([{}, {"skill": " "}, 42, None]), [])


if __name__ == "__main__":
    unittest.main()