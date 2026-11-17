"""Scoring Agent: scores each answer against the rubric, quoting the student's words.

Created by    : Mario Ciuciu
Date          : 17/11/2026

The LLM judges the answer; code decides and enforces everything it can:
- the rubric criterion (technical -> Technical accuracy, behavioural -> Structure (STAR)),
- that the evidence quote really appears in the student's answer,
- skipped answers are not scored, "I don't know" and injection attempts score 1 without
  the LLM, and very short answers cannot score above 2.
"""

import json
import re
from pathlib import Path

from src.agents.behavioural_interviewer import _looks_like_injection, _uses_first_person
from src.agents.technical_interviewer import _is_pass_or_unknown
from src.llm import format_data_context, generate_structured
from src.schemas import InterviewTurn, JobAnalysisOutput, ScoreOutput

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCORING_PROMPT = (PROJECT_ROOT / "prompts" / "scoring.md").read_text(encoding="utf-8")
RUBRIC = json.loads((PROJECT_ROOT / "data" / "rubric.json").read_text(encoding="utf-8"))

SKIP = "skip"  # how the UI stores a skipped answer: never scored
CRITERION_FOR_ROUND = {
    "technical": "Technical accuracy",
    "behavioural": "Structure (STAR)",
}
SHORT_ANSWER_WORDS = 10  # answers shorter than this cannot score above SHORT_ANSWER_MAX
SHORT_ANSWER_MAX = 2
MAX_QUOTE_WORDS = 25
# STAR answers that only say "we" are missing the candidate's own Action (Round 1, S4).
NO_PERSONAL_ACTION_MAX = 3


def _rubric_anchors(criterion: str) -> tuple[str, str]:
    """The rubric's descriptions of a 1 and a 5 for this criterion."""
    for item in RUBRIC["criteria"]:
        if item["name"] == criterion:
            return item["1"], item["5"]
    raise ValueError(f"Criterion '{criterion}' is not in data/rubric.json")


def _normalise(text: str) -> str:
    """Lowercase, straighten quotes and collapse spaces, so small copy differences still match."""
    text = text.lower().replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip(" \"'.,;:!?")


def _quote_in_answer(quote: str, answer: str) -> bool:
    """True if the quote (ignoring case, spacing and outer punctuation) appears in the answer."""
    return bool(_normalise(quote)) and _normalise(quote) in _normalise(answer)


def _shorten(quote: str) -> str:
    """Keep quotes readable: at most MAX_QUOTE_WORDS words (Round 1, S1)."""
    words = quote.split()
    return " ".join(words[:MAX_QUOTE_WORDS]) + (
        " ..." if len(words) > MAX_QUOTE_WORDS else ""
    )


def _fallback_quote(answer: str) -> str:
    """The answer's first sentence, shortened: always a genuine quote."""
    return _shorten(re.split(r"(?<=[.!?])\s+", answer.strip())[0])


def _fixed_score(criterion: str, answer: str, feedback: str) -> ScoreOutput:
    return ScoreOutput(
        score=1,
        rubric_criterion=criterion,
        evidence_quote=_fallback_quote(answer),
        actionable_feedback=feedback,
    )


def score_answer(
    turn: InterviewTurn, job_analysis: JobAnalysisOutput | None = None
) -> ScoreOutput | None:
    """Score one interview turn. Returns None for a skipped answer (not scored)."""
    answer = turn.student_answer.strip()
    criterion = CRITERION_FOR_ROUND[turn.question.round_type]

    if answer.lower() == SKIP:
        return None
    if _looks_like_injection(answer):
        return _fixed_score(
            criterion,
            answer,
            "Answer the question itself with a real example from your experience.",
        )
    if _is_pass_or_unknown(answer):
        return _fixed_score(
            criterion,
            answer,
            "Have a go even when unsure: explain what you do know and how you would find out the rest.",
        )

    score_1, score_5 = _rubric_anchors(criterion)
    level = job_analysis.experience_level if job_analysis else "Intern"
    prompt = (
        "Score the student's answer.\n\n"
        "DIRECTIVE:\n"
        f"CRITERION: {criterion}\n"
        f"SCORE_1: {score_1}\n"
        f"SCORE_5: {score_5}\n"
        f"LEVEL: {level}\n\n"
        f"{format_data_context(turn.question.question_text, 'question')}\n\n"
        f"{format_data_context(answer, 'answer')}"
    )

    for _attempt in range(2):
        generated = generate_structured(prompt, SCORING_PROMPT, ScoreOutput)
        if _quote_in_answer(generated.evidence_quote, answer):
            quote = _shorten(generated.evidence_quote.strip())
            break
        prompt += (
            "\n\nYour evidence_quote was not copied word for word from <answer>. "
            "Copy an exact phrase from the answer."
        )
    else:
        quote = _fallback_quote(
            answer
        )  # never show the student a quote they did not write

    score = generated.score
    if len(answer.split()) < SHORT_ANSWER_WORDS:
        score = min(score, SHORT_ANSWER_MAX)  # too short to show the skill properly
    if turn.question.round_type == "behavioural" and not _uses_first_person(answer):
        score = min(score, NO_PERSONAL_ACTION_MAX)  # only "we": no personal Action

    return ScoreOutput(
        score=score,
        rubric_criterion=criterion,  # enforced by code, whatever the LLM returned
        evidence_quote=quote,
        actionable_feedback=generated.actionable_feedback,
    )


def score_interview(
    history: list[InterviewTurn], job_analysis: JobAnalysisOutput | None = None
) -> list[InterviewTurn]:
    """Return a copy of the interview history with every turn's score filled in."""
    return [
        turn.model_copy(update={"score": score_answer(turn, job_analysis)})
        for turn in history
    ]


scoring_agent = score_interview
