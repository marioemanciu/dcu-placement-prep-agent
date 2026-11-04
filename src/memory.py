"""Long-term memory for weaknesses, scores and progress.

Raw CVs and full interview transcripts are never stored.
"""

import json
from pathlib import Path


class MemoryStore:
    """Stores a student's interview progress locally as JSON."""

    def __init__(self, directory: str = "memory_store"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _student_path(self, student_id: str) -> Path:
        """Return the local file used for one student's saved memory."""
        safe_id = "".join(
            character
            for character in student_id
            if character.isalnum() or character in ("-", "_")
        )

        if not safe_id:
            raise ValueError("student_id must contain letters or numbers")

        return self.directory / f"{safe_id}.json"

    def load(self, student_id: str) -> dict:
        """Retrieve saved weaknesses, scores and progress."""
        path = self._student_path(student_id)

        if not path.exists():
            return {
                "weaknesses": [],
                "scores": {},
                "progress": [],
            }

        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def save(
        self,
        student_id: str,
        weaknesses: list,
        scores: dict,
        progress: list | None = None,
        consent: bool = False,
    ) -> bool:
        """Save long-term memory only when the student has consented."""
        if not consent:
            return False

        data = {
            "weaknesses": weaknesses,
            "scores": scores,
            "progress": progress or [],
        }

        path = self._student_path(student_id)

        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

        return True

    def update(
        self,
        student_id: str,
        weaknesses: list | None = None,
        scores: dict | None = None,
        progress_entry: dict | None = None,
        consent: bool = False,
    ) -> bool:
        """Update an existing student's saved progress."""
        if not consent:
            return False

        data = self.load(student_id)

        if weaknesses is not None:
            data["weaknesses"] = weaknesses

        if scores is not None:
            data["scores"].update(scores)

        if progress_entry is not None:
            data["progress"].append(progress_entry)

        return self.save(
            student_id=student_id,
            weaknesses=data["weaknesses"],
            scores=data["scores"],
            progress=data["progress"],
            consent=True,
        )

    def delete(self, student_id: str) -> bool:
        """Delete all long-term memory for one student."""
        path = self._student_path(student_id)

        if path.exists():
            path.unlink()
            return True

        return False
