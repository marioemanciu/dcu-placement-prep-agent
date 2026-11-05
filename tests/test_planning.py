"""Unit tests for the Planning Agent's code rules.

These test _enforce_rules() and run() with a fake LLM, so they run without Ollama.
"""

import unittest
from unittest.mock import patch

from src.agents import planning
from src.schemas import JobAnalysisOutput, PlanningOutput, SkillEvidence


def make_gap(skill: str) -> SkillEvidence:
    return SkillEvidence(
        skill=skill, requirement_jd=f"Role requires {skill}", evidence_cv="None"
    )


JOB = JobAnalysisOutput(
    required_skills=["Python", "SQL", "Docker", "Communication", "Teamwork"],
    experience_level="Intern",
    likely_topics=["Databases", "Team projects"],
)


class TestPlanningRules(unittest.TestCase):
    def enforce(self, priority, technical, behavioural, candidates):
        plan = PlanningOutput(
            priority_gaps=priority,
            technical_focus=technical,
            behavioural_focus=behavioural,
        )
        return planning._enforce_rules(plan, candidates, JOB)

    def test_drops_invented_gaps(self):
        result = self.enforce(
            ["SQL", "Kubernetes"], ["SQL", "Kubernetes"], [], ["SQL", "Docker"]
        )

        self.assertEqual(result.priority_gaps, ["SQL"])
        self.assertNotIn("Kubernetes", result.technical_focus)

    def test_removes_duplicates_ignoring_case(self):
        result = self.enforce(
            ["sql", "SQL", "Docker"], ["SQL", "sql"], [], ["SQL", "Docker"]
        )

        self.assertEqual(result.priority_gaps, ["SQL", "Docker"])
        self.assertEqual(result.technical_focus, ["SQL"])

    def test_item_never_in_both_focus_lists(self):
        result = self.enforce(
            ["SQL", "Teamwork"], ["SQL", "Teamwork"], ["Teamwork"], ["SQL", "Teamwork"]
        )

        overlap = set(result.technical_focus) & set(result.behavioural_focus)
        self.assertEqual(overlap, set())

    def test_caps_list_lengths(self):
        gaps = ["A", "B", "C", "D", "E", "F", "G"]
        result = self.enforce(gaps, gaps, [], gaps)

        self.assertLessEqual(len(result.priority_gaps), planning.MAX_PRIORITY)
        self.assertLessEqual(len(result.technical_focus), planning.MAX_FOCUS)

    def test_behavioural_round_never_empty(self):
        result = self.enforce(
            ["SQL", "Docker"], ["SQL", "Docker"], [], ["SQL", "Docker"]
        )

        self.assertTrue(result.behavioural_focus)

    def test_behavioural_can_use_soft_skills_from_job(self):
        result = self.enforce(["SQL"], ["SQL"], ["Communication"], ["SQL"])

        self.assertIn("Communication", result.behavioural_focus)

    def test_behavioural_rejects_skills_not_in_job_or_gaps(self):
        result = self.enforce(["SQL"], ["SQL"], ["Leadership"], ["SQL"])

        self.assertNotIn("Leadership", result.behavioural_focus)


class TestPlanningRun(unittest.TestCase):
    def test_run_uses_likely_topics_when_no_gaps(self):
        fake_plan = PlanningOutput(
            priority_gaps=[], technical_focus=[], behavioural_focus=[]
        )

        with patch.object(planning, "generate_structured", return_value=fake_plan):
            result = planning.run([], JOB, None)

        self.assertEqual(result.priority_gaps, ["Databases", "Team projects"])

    def test_run_sends_past_weaknesses_to_llm(self):
        fake_plan = PlanningOutput(
            priority_gaps=["SQL"], technical_focus=["SQL"], behavioural_focus=[]
        )
        memory = {"weaknesses": ["Docker"], "scores": {}, "progress": []}

        with patch.object(
            planning, "generate_structured", return_value=fake_plan
        ) as fake_llm:
            planning.run([make_gap("SQL")], JOB, memory)

        user_prompt = fake_llm.call_args.args[0]
        self.assertIn("<past_weaknesses>", user_prompt)
        self.assertIn("Docker", user_prompt)


if __name__ == "__main__":
    unittest.main()
