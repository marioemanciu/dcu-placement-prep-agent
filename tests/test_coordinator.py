"""Automated tests for Coordinator execution control."""

import unittest

from src.coordinator import Coordinator, CoordinatorError, SessionStage
from src.schemas import (
    GapAnalysisOutput,
    JobAnalysisOutput,
    PlanningOutput,
    SkillEvidence,
)


def valid_job_analysis(job_description):
    return JobAnalysisOutput(
        required_skills=["Python", "SQL"],
        experience_level="Intern",
        likely_topics=["Python", "Databases"],
    )


def valid_gap_analysis(cv_text, job_analysis, previous_memory):
    return GapAnalysisOutput(
        strengths=[
            SkillEvidence(
                skill="Python",
                requirement_jd="Python required",
                evidence_cv="Python project",
            )
        ],
        gaps=[
            SkillEvidence(
                skill="SQL",
                requirement_jd="SQL required",
                evidence_cv="None",
            ),
            SkillEvidence(
                skill="Git",
                requirement_jd="Git required",
                evidence_cv="None",
            ),
        ],
    )


class CoordinatorTests(unittest.TestCase):

    def make_coordinator(self, planning_agent=None):
        if planning_agent is None:
            planning_agent = self.valid_planning

        return Coordinator(
            job_analysis_agent=valid_job_analysis,
            gap_analysis_agent=valid_gap_analysis,
            planning_agent=planning_agent,
        )

    @staticmethod
    def valid_planning(gaps, job_analysis, previous_memory):
        return PlanningOutput(
            priority_gaps=[gap.skill for gap in gaps],
            technical_focus=[gap.skill for gap in gaps],
            behavioural_focus=["Problem solving"],
        )

    def test_invalid_output_is_retried_once(self):
        attempts = {"count": 0}

        def flaky_job_analysis(job_description):
            attempts["count"] += 1

            if attempts["count"] == 1:
                return {"required_skills": ["Python"]}

            return valid_job_analysis(job_description)

        coordinator = Coordinator(
            job_analysis_agent=flaky_job_analysis,
            gap_analysis_agent=valid_gap_analysis,
            planning_agent=self.valid_planning,
        )

        result = coordinator.run_analysis(
            "Python experience",
            "Intern role requiring Python and SQL",
            "student_retry",
        )

        self.assertEqual(attempts["count"], 2)
        self.assertEqual(result["stage"], "h1_pending")

    def test_h1_rejection_changes_stage(self):
        coordinator = self.make_coordinator()

        coordinator.run_analysis(
            "Python experience",
            "Intern role requiring Python and SQL",
            "student_reject",
        )

        coordinator.confirm_analysis(approved=False)

        self.assertEqual(
            coordinator.stage,
            SessionStage.ANALYSIS_REJECTED,
        )

    def test_modified_gaps_trigger_replanning(self):
        planning_calls = []

        def planning_agent(gaps, job_analysis, previous_memory):
            planning_calls.append([gap.skill for gap in gaps])

            return PlanningOutput(
                priority_gaps=[gap.skill for gap in gaps],
                technical_focus=[gap.skill for gap in gaps],
                behavioural_focus=["Problem solving"],
            )

        coordinator = self.make_coordinator(planning_agent)

        result = coordinator.run_analysis(
            "Python experience",
            "Intern role requiring Python, SQL and Git",
            "student_modify",
        )

        sql_only = [result["proposed_gaps"][0]]

        state = coordinator.confirm_analysis(
            approved=True,
            confirmed_gaps=sql_only,
        )

        self.assertEqual(
            planning_calls,
            [["SQL", "Git"], ["SQL"]],
        )
        self.assertEqual(
            state.plan.priority_gaps,
            ["SQL"],
        )

    def test_illegal_stage_transition_is_blocked(self):
        coordinator = self.make_coordinator()

        coordinator.run_analysis(
            "Python experience",
            "Intern role requiring Python and SQL",
            "student_stage",
        )

        coordinator.confirm_analysis(approved=True)

        with self.assertRaises(CoordinatorError):
            coordinator.run_analysis(
                "Another CV",
                "Another JD",
                "student_stage",
            )

    def test_snapshot_is_safe_and_reset_clears_session(self):
        coordinator = self.make_coordinator()

        coordinator.run_analysis(
            "Python experience",
            "Intern role requiring Python and SQL",
            "student_reset",
        )

        snapshot = coordinator.snapshot()

        self.assertNotIn("cv_text", str(snapshot))
        self.assertNotIn("job_description", str(snapshot))

        coordinator.reset_session()

        self.assertEqual(
            coordinator.stage,
            SessionStage.INTAKE,
        )
        self.assertEqual(coordinator.context, {})


if __name__ == "__main__":
    unittest.main()
