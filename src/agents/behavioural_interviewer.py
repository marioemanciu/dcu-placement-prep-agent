"""Behavioural Interviewer: asks STAR questions and follows up on missing parts."""

# Created by    : Mario Ciuciu
# Date          : 12/11/2026

# Same contract as the Technical Interviewer, so both rounds run through one loop:
# generate_behavioural_question(behavioural_focus, job_analysis, interview_history) -> InterviewQuestion
# The code decides the topic and whether to ask a follow-up; the LLM only writes the
# question text. The UI/Coordinator decides when the round ends.


import json
from pathlib import Path
from typing import Any


from src.agents.technical_interviewer import _is_pass_or_unknown
from src.llm import format_data_context, generate_structured
from src.schemas import InterviewQuestion, InterviewTurn, JobAnalysisOutput, SchemaModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUESTION_PROMPT = (PROJECT_ROOT / "prompts" / "behavioural_interviewer.md").read_text(
    encoding="utf-8"
)
STAR_PROMPT = (PROJECT_ROOT / "prompts" / "star_check.md").read_text(encoding="utf-8")
STAR_PARTS = ("situation", "task", "action", "result")


class StarCheck(SchemaModel):
    """Which STAR parts an answer contains (internal to this agent)."""

    situation: bool
    task: bool
    action: bool
    result: bool

    def missing(self) -> list[str]:
        return [part for part in STAR_PARTS if not getattr(self, part)]


def check_star(question: str, answer: str) -> StarCheck:
    """Ask the LLM which STAR parts the answer covers. The answer is untrusted data."""
    prompt = "\n\n".join(
        [
            "Check which STAR parts the candidate's answer contains.",
            format_data_context(question, "question"),
            format_data_context(answer, "answer"),
        ]
    )
    return generate_structured(prompt, STAR_PROMPT, StarCheck)


def _load_examples() -> list[Any]:
    """Behavioural example questions; an empty list if the bank is missing or malformed."""
    try:
        bank = json.loads(
            (PROJECT_ROOT / "data" / "question_bank.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return []
    examples = bank.get("behavioural") if isinstance(bank, dict) else None
    return examples if isinstance(examples, list) else []


def _behavioural_turns(
    history: list[InterviewTurn] | list[dict] | None,
) -> list[InterviewTurn]:
    """Validate the history and keep only behavioural turns, in conversation order."""
    turns = [
        item if isinstance(item, InterviewTurn) else InterviewTurn.model_validate(item)
        for item in (history or [])
    ]
    behavioural = [t for t in turns if t.question.round_type == "behavioural"]
    return sorted(behavioural, key=lambda t: t.turn_index)


def _job_context(job_analysis: JobAnalysisOutput | dict | None) -> str:
    if job_analysis is None:
        return "{}"
    if isinstance(job_analysis, dict):
        job_analysis = JobAnalysisOutput.model_validate(job_analysis)
    return job_analysis.model_dump_json(indent=2)


def _next_topic(focus: list[str], turns: list[InterviewTurn]) -> str:
    """The first unasked competency; if all were asked, the one asked least often."""
    main_counts = {topic: 0 for topic in focus}
    for turn in turns:
        topic = turn.question.target_skill_or_gap
        if topic in main_counts and not turn.question.is_followup:
            main_counts[topic] += 1
    return min(
        focus, key=lambda topic: main_counts[topic]
    )  # min keeps focus order on ties


def generate_behavioural_question(
    behavioural_focus: list[str],
    job_analysis: JobAnalysisOutput | dict | None = None,
    interview_history: list[InterviewTurn] | list[dict] | None = None,
) -> InterviewQuestion:
    """Generate the next behavioural question: a STAR follow-up or a new competency."""
    if (
        not isinstance(behavioural_focus, list)
        or not behavioural_focus
        or any(not isinstance(c, str) or not c.strip() for c in behavioural_focus)
    ):
        raise ValueError(
            "behavioural_focus must be a non-empty list of non-blank strings"
        )

    focus = [c.strip() for c in behavioural_focus]
    turns = _behavioural_turns(interview_history)
    last = turns[-1] if turns else None
    missing: list[str] = []

    # Decide the topic and whether this is a follow-up (code, not the LLM, decides).
    if last is None:
        mode = "INITIAL_QUESTION"
    elif _is_pass_or_unknown(last.student_answer):
        mode = "NEXT_TOPIC_AFTER_PASS"  # H2: a skipped answer is never followed up
    elif last.question.is_followup:
        mode = "NEXT_TOPIC_AFTER_FOLLOW_UP"  # at most one follow-up per competency
    else:
        missing = check_star(last.question.question_text, last.student_answer).missing()
        mode = "STAR_FOLLOW_UP" if missing else "NEXT_TOPIC_COMPLETE_STAR"

    is_followup = mode == "STAR_FOLLOW_UP"
    target = (
        last.question.target_skill_or_gap if is_followup else _next_topic(focus, turns)
    )

    asked = {t.question.target_skill_or_gap for t in turns}
    focus_data = json.dumps(
        {
            "all_focus_competencies": focus,
            "unasked": [c for c in focus if c not in asked],
        },
        indent=2,
    )
    history_data = json.dumps(
        [
            {
                "competency": t.question.target_skill_or_gap,
                "question_text": t.question.question_text,
                "student_answer": t.student_answer,
                "is_followup": t.question.is_followup,
            }
            for t in turns
        ],
        ensure_ascii=False,
        indent=2,
    )
    prompt = (
        "Generate the next behavioural interview question. Set round_type to 'behavioural'.\n\n"
        "DIRECTIVE:\n"
        f"TARGET_COMPETENCY: {target}\n"
        f"IS_FOLLOWUP: {str(is_followup).lower()}\n"
        f"MISSING_STAR: {', '.join(missing) if missing else 'none'}\n"
        f"MODE: {mode}\n\n"
        f"{format_data_context(focus_data, 'behavioural_focus')}\n\n"
        f"{format_data_context(_job_context(job_analysis), 'job_context')}\n\n"
        f"{format_data_context(history_data, 'interview_history')}\n\n"
        f"{format_data_context(json.dumps(_load_examples(), indent=2), 'question_bank')}"
    )

    previous = {t.question.question_text.strip().casefold() for t in turns}
    for attempt in range(2):
        generated = generate_structured(prompt, QUESTION_PROMPT, InterviewQuestion)
        # Enforce the fields this agent controls, whatever the LLM returned.
        result = InterviewQuestion(
            question_text=generated.question_text,
            target_skill_or_gap=target,
            round_type="behavioural",
            is_followup=is_followup,
        )
        if result.question_text.strip().casefold() not in previous:
            return result
        prompt += (
            "\n\nYour last question repeated an earlier one. Ask a different question."
        )
    raise ValueError("The generated behavioural question repeats a previous question.")


behavioural_interviewer_agent = generate_behavioural_question
