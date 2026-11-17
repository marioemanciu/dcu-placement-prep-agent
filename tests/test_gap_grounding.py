"""CV grounding for the Gap-analysis Agent (found in UI5 live testing), fake LLM only."""

import unittest
from unittest.mock import patch

from src.agents import gap_analysis as gap
from src.schemas import GapAnalysisOutput, JobAnalysisOutput, SkillEvidence

CV = (
    "Alex Murphy\n"
    "Skills: Python, Java, Git, Linux, Teamwork\n"
    "Study planner web app (Python, Flask): built in a team of four; I handled the backend.\n"
    "Java chess engine: solo project implementing move generation and unit tests.\n"
)


def item(skill, evidence="None"):
    return SkillEvidence(
        skill=skill, requirement_jd=f"Requires {skill}", evidence_cv=evidence
    )


def ground(strengths=(), gaps=()):
    return gap._ground_in_cv(
        GapAnalysisOutput(strengths=list(strengths), gaps=list(gaps)), CV
    )


def skills(items):
    return [i.skill for i in items]


class TestGrounding(unittest.TestCase):
    def test_real_evidence_is_kept(self):
        result = ground(
            strengths=[item("Git", "Skills: Python, Java, Git, Linux, Teamwork")]
        )
        self.assertEqual(
            result.strengths[0].evidence_cv,
            "Skills: Python, Java, Git, Linux, Teamwork",
        )

    def test_required_skill_left_out_by_llm_is_added(self):  # UI6: Git
        result = gap._ground_in_cv(
            GapAnalysisOutput(strengths=[], gaps=[item("Docker")]),
            CV,
            ["Git", "Docker", "AWS"],
        )
        self.assertEqual(skills(result.strengths), ["Git"])
        self.assertEqual(skills(result.gaps), ["Docker", "AWS"])

    def test_invented_evidence_for_skill_not_in_cv_becomes_gap(self):  # UI5: FastAPI
        result = ground(
            strengths=[
                item("FastAPI", "Developed backend APIs using Python and FastAPI.")
            ]
        )
        self.assertEqual(skills(result.strengths), [])
        self.assertEqual(skills(result.gaps), ["FastAPI"])
        self.assertEqual(result.gaps[0].evidence_cv, "None")

    def test_invented_evidence_for_skill_in_cv_is_replaced_with_real_line(
        self,
    ):  # UI5: Python
        result = ground(
            strengths=[
                item("Python", "Developed backend APIs using Python and FastAPI.")
            ]
        )
        self.assertEqual(skills(result.strengths), ["Python"])
        self.assertIn(result.strengths[0].evidence_cv.rstrip(" ."), CV)

    def test_gap_named_in_cv_becomes_strength(self):  # UI5: Flask
        result = ground(gaps=[item("Flask"), item("Docker")])
        self.assertEqual(skills(result.strengths), ["Flask"])
        self.assertIn("Flask", result.strengths[0].evidence_cv)
        self.assertEqual(skills(result.gaps), ["Docker"])

    def test_gap_with_invented_evidence_is_reset_to_none(self):
        result = ground(gaps=[item("Docker", "Deployed services with Docker")])
        self.assertEqual(result.gaps[0].evidence_cv, "None")

    def test_whole_word_match_only(self):
        self.assertIsNone(gap._cv_line_naming("Java", "I wrote JavaScript only."))
        self.assertIsNone(gap._cv_line_naming("C", "I like cats."))

    def test_analyze_gaps_applies_grounding(self):
        llm_output = GapAnalysisOutput(
            strengths=[
                item("FastAPI", "Developed backend APIs using Python and FastAPI.")
            ],
            gaps=[item("Flask")],
        )
        job = JobAnalysisOutput(
            required_skills=["FastAPI", "Flask"],
            experience_level="Intern",
            likely_topics=["APIs"],
        )
        with patch.object(gap, "generate_structured", return_value=llm_output):
            result = gap.analyze_gaps(CV, job)

        self.assertEqual(skills(result.strengths), ["Flask"])
        self.assertEqual(skills(result.gaps), ["FastAPI"])


if __name__ == "__main__":
    unittest.main()
