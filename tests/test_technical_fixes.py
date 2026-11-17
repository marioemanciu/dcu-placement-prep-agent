"""Technical Interviewer fixes found in UI7 live testing (fake LLM, no Ollama)."""

import unittest
from unittest.mock import patch

from src.agents import technical_interviewer as ti
from src.schemas import InterviewQuestion, InterviewTurn

FOCUS = ["Docker", "SQL", "FastAPI"]


def q(text, skill, followup=False):
    return InterviewQuestion(
        question_text=text,
        target_skill_or_gap=skill,
        round_type="technical",
        is_followup=followup,
    )


def turn(index, question, answer):
    return InterviewTurn(turn_index=index, question=question, student_answer=answer)


def reply(text):
    """Fake LLM reply with deliberately wrong fields (the agent must override them)."""
    return q(text, "Wrong", followup=False)


class TestNextTopic(unittest.TestCase):
    def test_after_pass_does_not_repeat_the_skill_just_asked(self):  # UI7: Docker twice
        history = [
            turn(0, q("Explain Docker images.", "Docker"), "no"),
            turn(
                1, q("How do you optimise SQL queries?", "SQL"), "Query what you need"
            ),
            turn(2, q("What are SQL indexes?", "SQL", followup=True), "skip"),
            turn(3, q("Why use FastAPI?", "FastAPI"), "no"),
            turn(4, q("How do Docker volumes work?", "Docker"), "idk"),
        ]
        with patch.object(
            ti, "generate_structured", return_value=reply("What is a SQL transaction?")
        ):
            result = ti.generate_technical_question(FOCUS, None, history)

        self.assertEqual(result.target_skill_or_gap, "SQL")
        self.assertFalse(result.is_followup)


class TestFollowUpHistory(unittest.TestCase):
    def test_follow_up_prompt_only_has_current_skill(
        self,
    ):  # UI7: SQL follow-up about Docker
        history = [
            turn(0, q("Explain Docker container isolation.", "Docker"), "no"),
            turn(
                1, q("How do you optimise SQL queries?", "SQL"), "Query what you need"
            ),
        ]
        with patch.object(
            ti,
            "generate_structured",
            return_value=reply("When would an index slow a query down?"),
        ) as llm:
            result = ti.generate_technical_question(FOCUS, None, history)

        self.assertTrue(result.is_followup)
        self.assertEqual(result.target_skill_or_gap, "SQL")
        self.assertNotIn("container isolation", llm.call_args.args[0])


class TestRepeats(unittest.TestCase):
    HISTORY = [
        turn(
            0,
            q(
                "What are the primary benefits and trade-offs of using Docker's containerization "
                "technology for application deployment?",
                "Docker",
            ),
            "skip",
        )
    ]

    def test_near_duplicate_is_retried(self):
        replies = iter(
            [
                reply(
                    "What are the primary benefits and trade-offs of using Docker's containerization "
                    "technology for application deployment in production?"
                ),
                reply("How would you write a SQL query to find duplicate rows?"),
            ]
        )
        with patch.object(
            ti, "generate_structured", side_effect=lambda *a: next(replies)
        ) as llm:
            result = ti.generate_technical_question(FOCUS, None, self.HISTORY)

        self.assertEqual(llm.call_count, 2)
        self.assertIn("duplicate rows", result.question_text)

    def test_repeat_twice_still_raises(self):
        same = reply(self.HISTORY[0].question.question_text)
        with patch.object(ti, "generate_structured", return_value=same):
            with self.assertRaises(ValueError):
                ti.generate_technical_question(FOCUS, None, self.HISTORY)

    def test_different_question_on_same_skill_is_allowed(self):
        self.assertFalse(
            ti._too_similar(
                "How do Docker volumes persist data?",
                [self.HISTORY[0].question.question_text],
            )
        )


if __name__ == "__main__":
    unittest.main()
