"""Behavioural Interviewer: asks STAR questions and follows up on missing parts."""

# Created by    : Mario Ciuciu
# Date          : 12/11/2026

# Same contract as the Technical Interviewer, so both rounds run through one loop:
# generate_behavioural_question(behavioural_focus, job_analysis, interview_history) -> InterviewQuestion
# The code decides the topic and whether to ask a follow-up; the LLM only writes the
# question text. The UI/Coordinator decides when the round ends.


import json
import re
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

# An answer this short cannot realistically cover all four STAR parts, so it always gets
# a follow-up even if the LLM says it is complete (found in Round 1 testing, B6).
MIN_COMPLETE_WORDS = 20
# Phrases that try to instruct the agent instead of answering the question.
INJECTION_PHRASES = (
    "ignore all",
    "ignore previous",
    "ignore the above",
    "previous instructions",
    "disregard",
    "mark every",
    "mark all",
    "you are now",
    "system prompt",
)

# Words showing the candidate describes their OWN actions, not only the team's (Round 3, B5).
FIRST_PERSON = {"i", "i'm", "i've", "i'd", "i'll", "my", "me", "myself"}

# Fixed question when the answer contained no usable STAR detail at all (Round 4, B6).
REAL_EXAMPLE_QUESTION = (
    "Please describe one specific real situation that shows your {competency}: what was the "
    "situation, what was your task, what did you personally do, and what was the result?"
)


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


def _looks_like_injection(answer: str) -> bool:
    """True if the answer contains phrases that try to instruct the agent."""
    text = answer.lower()
    return any(phrase in text for phrase in INJECTION_PHRASES)


def _uses_first_person(answer: str) -> bool:
    """True if the answer says anything about what the candidate personally did."""
    return any(word in FIRST_PERSON for word in re.findall(r"[a-z']+", answer.lower()))


def _missing_star_parts(question: str, answer: str) -> list[str]:
    """STAR parts still missing, combining the LLM check with code-level sanity rules."""
    if _looks_like_injection(answer):
        return list(STAR_PARTS)  # not a real answer: ask for a real example
    missing = check_star(question, answer).missing()
    if "action" not in missing and not _uses_first_person(answer):
        missing = [part for part in STAR_PARTS if part in missing or part == "action"]
    if not missing and len(answer.split()) < MIN_COMPLETE_WORDS:
        return ["action", "result"]  # too short to be complete: ask for more detail
    return missing


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
    # Only the level: behavioural questions must not pick up technical skills (Round 5, B1).
    return json.dumps({"experience_level": job_analysis.experience_level})


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
        missing = _missing_star_parts(last.question.question_text, last.student_answer)
        mode = "STAR_FOLLOW_UP" if missing else "NEXT_TOPIC_COMPLETE_STAR"

    is_followup = mode == "STAR_FOLLOW_UP"
    target = (
        last.question.target_skill_or_gap if is_followup else _next_topic(focus, turns)
    )

    # Only the target is sent, so the LLM cannot blend in other competencies (Round 4, B1).
    focus_data = json.dumps({"target_competency": target}, indent=2)
        # Follow-ups see only this competency's turns, so other questions cannot bleed in (UI6).
    shown = [t for t in turns if t.question.target_skill_or_gap == target] if is_followup else turns

    history_data = json.dumps(
        [
            {
                "competency": t.question.target_skill_or_gap,
                "question_text": t.question.question_text,
                "student_answer": t.student_answer,
                "is_followup": t.question.is_followup,
            }
            for t in shown
        ],
        ensure_ascii=False,
        indent=2,
    )

    # Follow-ups use only the candidate's own words, never job details (Round 2: B2, B6).
    job_text = "{}" if is_followup else _job_context(job_analysis)

    examples = [] if is_followup else _load_examples()

    prompt = (
        "Generate the next behavioural interview question. Set round_type to 'behavioural'.\n\n"
        "DIRECTIVE:\n"
        f"TARGET_COMPETENCY: {target}\n"
        f"IS_FOLLOWUP: {str(is_followup).lower()}\n"
        f"MISSING_STAR: {', '.join(missing) if missing else 'none'}\n"
        f"MODE: {mode}\n\n"
        f"{format_data_context(focus_data, 'behavioural_focus')}\n\n"
        f"{format_data_context(job_text, 'job_context')}\n\n"
        f"{format_data_context(history_data, 'interview_history')}\n\n"
        f"{format_data_context(json.dumps(examples, indent=2), 'question_bank')}"
    )

    if is_followup and _looks_like_injection(last.student_answer):
        # No usable answer (e.g. an injection): ask for a real example without the LLM.
        return InterviewQuestion(
            question_text=REAL_EXAMPLE_QUESTION.format(competency=target.lower()),
            target_skill_or_gap=target,
            round_type="behavioural",
            is_followup=True,
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
