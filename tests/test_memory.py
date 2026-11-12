"""Automated tests for consent-based long-term memory."""

import tempfile
import unittest

from src.memory import MemoryStore


class MemoryStoreTests(unittest.TestCase):

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.memory = MemoryStore(self.temp_directory.name)
        self.student_id = "test_student"

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_no_consent_does_not_save(self):
        saved = self.memory.save(
            self.student_id,
            weaknesses=["SQL"],
            scores={"technical": 2},
            consent=False,
        )

        self.assertFalse(saved)
        self.assertEqual(
            self.memory.load(self.student_id),
            {
                "weaknesses": [],
                "scores": {},
                "progress": [],
            },
        )

    def test_consent_saves_memory(self):
        saved = self.memory.save(
            self.student_id,
            weaknesses=["SQL"],
            scores={"technical": 2},
            consent=True,
        )

        self.assertTrue(saved)

        data = self.memory.load(self.student_id)

        self.assertEqual(data["weaknesses"], ["SQL"])
        self.assertEqual(data["scores"], {"technical": 2})

    def test_update_changes_progress(self):
        self.memory.save(
            self.student_id,
            weaknesses=["SQL"],
            scores={"technical": 2},
            consent=True,
        )

        self.memory.update(
            self.student_id,
            weaknesses=["SQL joins"],
            scores={"technical": 3},
            progress_entry={"session": 2, "technical": 3},
            consent=True,
        )

        data = self.memory.load(self.student_id)

        self.assertEqual(data["weaknesses"], ["SQL joins"])
        self.assertEqual(data["scores"]["technical"], 3)
        self.assertEqual(len(data["progress"]), 1)

    def test_delete_removes_memory(self):
        self.memory.save(
            self.student_id,
            weaknesses=["SQL"],
            scores={"technical": 2},
            consent=True,
        )

        deleted = self.memory.delete(self.student_id)

        self.assertTrue(deleted)
        self.assertEqual(
            self.memory.load(self.student_id)["weaknesses"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
