"""Unit tests for the Report Generator (no LLM involved)."""

import unittest
from io import BytesIO

from docx import Document

from src.schemas import (
    InterviewQuestion,
    InterviewTurn,
    JobAnalysisOutput,
    PlanningOutput,
    ScoreOutput,
    SkillEvidence,
)
from src.tools import report

JOB = JobAnalysisOutput(
    required_skills=["Python", "SQL", "Teamwork"],
    experience_level="Intern",
    likely_topics=["SQL"],
)
STRENGTHS = [
    SkillEvidence(
        skill="Python", requirement_jd="Python", evidence_cv="Built a FastAPI backend"
    )
]
GAPS = [SkillEvidence(skill="SQL", requirement_jd="Requires SQL", evidence_cv="None")]
PLAN = PlanningOutput(
    priority_gaps=["SQL"], technical_focus=["SQL"], behavioural_focus=["Teamwork"]
)


def turn(index, topic, round_type, answer, score=None, followup=False):
    return InterviewTurn(
        turn_index=index,
        question=InterviewQuestion(
            question_text=f"Question about {topic} {index}?",
            target_skill_or_gap=topic,
            round_type=round_type,
            is_followup=followup,
        ),
        student_answer=answer,
        score=(
            None
            if score is None
            else ScoreOutput(
                score=score,
                rubric_criterion=(
                    "Technical accuracy"
                    if round_type == "technical"
                    else "Structure (STAR)"
                ),
                evidence_quote=answer[:20],
                actionable_feedback="Give a concrete example.",
            )
        ),
    )


HISTORY = [
    turn(0, "SQL", "technical", "A join combines rows from two tables.", score=4),
    turn(1, "SQL", "technical", "I am not sure about indexes.", score=2, followup=True),
    turn(2, "Teamwork", "behavioural", "skip"),
    turn(
        3,
        "Teamwork",
        "behavioural",
        "I led our sprint planning and we shipped on time.",
        score=5,
    ),
]


def report_text(data: bytes) -> str:
    return "\n".join(p.text for p in Document(BytesIO(data)).paragraphs)


class TestHelpers(unittest.TestCase):
    def test_round_average_ignores_unscored_turns(self):
        self.assertEqual(report.round_average(HISTORY, "technical"), 3.0)
        self.assertEqual(report.round_average(HISTORY, "behavioural"), 5.0)

    def test_round_average_none_when_nothing_scored(self):
        self.assertIsNone(
            report.round_average([turn(0, "SQL", "technical", "skip")], "technical")
        )

    def test_weak_topics_include_low_scores_and_skips_once(self):
        self.assertEqual(report.weak_topics(HISTORY), ["SQL", "Teamwork"])


class TestBuildReport(unittest.TestCase):
    def setUp(self):
        self.text = report_text(
            report.build_report(JOB, STRENGTHS, GAPS, PLAN, HISTORY, "alex")
        )

    def test_has_all_sections(self):
        for heading in [
            "1. The role",
            "2. Your strengths",
            "3. Gaps you practised",
            "4. Practice plan",
            "5. Interview results",
            "6. What to work on next",
        ]:
            self.assertIn(heading, self.text)

    def test_shows_scores_averages_and_feedback(self):
        self.assertIn("Technical round: average 3.0/5", self.text)
        self.assertIn("Score: 4/5", self.text)
        self.assertIn("Give a concrete example.", self.text)
        self.assertIn("(follow-up)", self.text)

    def test_skipped_answer_is_marked_not_scored(self):
        self.assertIn("(skipped)", self.text)
        self.assertIn("Skipped answers are not scored.", self.text)

    def test_uses_cv_evidence_not_raw_cv(self):
        self.assertIn("Built a FastAPI backend", self.text)

    def test_empty_interview_still_builds(self):
        text = report_text(report.build_report(JOB, [], [], PLAN, []))
        self.assertIn("No interview was completed in this session.", text)
        self.assertIn("No weak areas found", text)


if __name__ == "__main__":
    unittest.main()
