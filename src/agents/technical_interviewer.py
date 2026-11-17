# Technical Interview Agent - asks role-specific questions and adapts follow-ups.
#
# Created by    : Maksym Sharai
# Date          : 12/11/2026
# Edited by : Mario Ciuciu (17/11/2026)

import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Make the project root importable when this file is run directly as a script.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.llm import format_data_context, generate_structured
from src.schemas import InterviewQuestion, InterviewTurn, JobAnalysisOutput

SYSTEM_PROMPT = (PROJECT_ROOT / "prompts" / "technical_interviewer.md").read_text(
    encoding="utf-8"
)


def load_question_templates() -> list[Any]:
    """Load technical question templates, returning an empty list if unavailable."""

    question_bank_path = PROJECT_ROOT / "data" / "question_bank.json"
    try:
        # A missing or malformed question bank should not prevent interview questions.
        question_bank = json.loads(question_bank_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if not isinstance(question_bank, dict):
        return []
    technical_questions = question_bank.get("technical")
    return technical_questions if isinstance(technical_questions, list) else []


def _normalize_job_analysis(
    job_analysis: JobAnalysisOutput | dict[str, Any] | None,
) -> str:
    # Convert supported inputs into the same JSON text format for the prompt.
    if job_analysis is None:
        normalized = {}
    elif isinstance(job_analysis, JobAnalysisOutput):
        normalized = job_analysis.model_dump(mode="json")
    elif isinstance(job_analysis, dict):
        normalized = JobAnalysisOutput.model_validate(job_analysis).model_dump(
            mode="json"
        )
    else:
        raise ValueError(
            "job_analysis must be a JobAnalysisOutput, dictionary, or None"
        )
    return json.dumps(normalized, ensure_ascii=False, indent=2)


def _normalize_interview_history(
    interview_history: list[InterviewTurn] | list[dict[str, Any]] | None,
) -> str:
    # Validate each turn, then sort so later decisions use the true conversation order.
    if interview_history is None:
        turns: list[InterviewTurn] = []
    elif not isinstance(interview_history, list):
        raise ValueError("interview_history must be a list or None")
    else:
        turns = []
        for item in interview_history:
            if isinstance(item, InterviewTurn):
                turns.append(item)
            elif isinstance(item, dict):
                turns.append(InterviewTurn.model_validate(item))
            else:
                raise ValueError(
                    "Each interview_history entry must be an InterviewTurn or dictionary"
                )

    chronological_turns = sorted(turns, key=lambda turn: turn.turn_index)
    history_data = [
        {
            "turn_index": turn.turn_index,
            "target_skill": turn.question.target_skill_or_gap,
            "question_text": turn.question.question_text,
            "student_answer": turn.student_answer,
            "is_followup": turn.question.is_followup,
        }
        for turn in chronological_turns
    ]
    return json.dumps(history_data, ensure_ascii=False, indent=2)


def _is_pass_or_unknown(answer: str) -> bool:
    """Return whether an answer explicitly passes or indicates no knowledge."""

    if not isinstance(answer, str):
        return False

    # Normalize punctuation and spacing so common variations match the same phrases.
    normalized = answer.lower().replace("’", "'").replace("`", "'")
    normalized = re.sub(r"[^\w']+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"\bn\s+a\b", "n/a", normalized)
    pass_phrases = (
        "don't know",
        "dont know",
        "do not know",
        "no idea",
        "no clue",
        "not sure",
        "haven't worked",
        "have not worked",
        "never used",
        "not familiar",
        "no experience",
        "can't answer",
        "cannot answer",
        "blanking",
        "unsure",
        "next question",
    )
    if any(
        re.search(rf"\b{re.escape(phrase)}\b", normalized) for phrase in pass_phrases
    ):
        return True

    short_passes = {
        "no",
        "nope",
        "idk",
        "pass",
        "skip",
        "n/a",
    }
    return len(normalized.split()) <= 2 and normalized in short_passes


# ---------- Added by Mario Ciuciu, 17/11/2026, after UI7 live testing ----------
# UI7 showed a follow-up about SQL drifting into Docker (the prompt saw every topic),
# and the same Docker question asked twice in a row (next topic fell back to
# cleaned_focus[0], and only exact repeats were caught).
SIMILARITY_LIMIT = 0.7  # questions sharing this share of their words count as repeats


def _next_topic(focus: list[str], history_turns: list[dict[str, Any]]) -> str:
    """The first unasked skill; otherwise the least-asked one, never the skill just asked."""
    counts = {skill: 0 for skill in focus}
    for turn in history_turns:
        if turn.get("target_skill") in counts and not turn.get("is_followup"):
            counts[turn["target_skill"]] += 1
    last_skill = history_turns[-1].get("target_skill") if history_turns else None
    options = [skill for skill in focus if skill != last_skill] or focus
    return min(
        options, key=lambda skill: counts[skill]
    )  # min keeps focus order on ties


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9']+", text.lower()) if len(word) > 3}


def _too_similar(question: str, previous: list[str]) -> bool:
    """True if the question repeats an earlier one exactly or with mostly the same words."""
    words = _words(question)
    for old in previous:
        if question.strip().casefold() == old.strip().casefold():
            return True
        old_words = _words(old)
        if (
            words
            and old_words
            and len(words & old_words) / len(words | old_words) >= SIMILARITY_LIMIT
        ):
            return True
    return False


def generate_technical_question(
    technical_focus: list[str],
    job_analysis: JobAnalysisOutput | dict[str, Any] | None = None,
    interview_history: list[InterviewTurn] | list[dict[str, Any]] | None = None,
) -> InterviewQuestion:
    """Generate an adaptive technical interview question for the next turn."""

    if (
        not isinstance(technical_focus, list)
        or not technical_focus
        or any(
            not isinstance(skill, str) or not skill.strip() for skill in technical_focus
        )
    ):
        raise ValueError(
            "technical_focus must be a non-empty list of non-blank strings"
        )

    # Clean focus names before comparing them with skills already covered in history.
    cleaned_focus = [skill.strip() for skill in technical_focus]
    job_context = _normalize_job_analysis(job_analysis)
    history_context = _normalize_interview_history(interview_history)
    history_turns = json.loads(history_context) if history_context else []
    asked_skills = {
        turn.get("target_skill") for turn in history_turns if turn.get("target_skill")
    }
    unasked_skills = [skill for skill in cleaned_focus if skill not in asked_skills]
    # The most recent answer determines whether to probe further or move to another skill.
    last_turn = history_turns[-1] if history_turns else None
    last_turn_was_followup = (
        last_turn.get("is_followup", False) if last_turn is not None else False
    )
    candidate_passed = (
        _is_pass_or_unknown(last_turn["student_answer"])
        if last_turn is not None
        else False
    )
    if last_turn is None:
        # Start with the first focus area when there is no previous conversation.
        target_skill = _next_topic(cleaned_focus, history_turns)
        force_followup = False
        mode = "INITIAL_QUESTION"
    elif candidate_passed or last_turn_was_followup:
        # A pass or a completed follow-up ends this topic and advances the interview.
        target_skill = _next_topic(cleaned_focus, history_turns)
        force_followup = False
        mode = (
            "NEXT_TOPIC_AFTER_PASS"
            if candidate_passed
            else "NEXT_TOPIC_AFTER_FOLLOW_UP"
        )
    else:
        # Otherwise, use the same skill for a deeper follow-up question.
        target_skill = last_turn["target_skill"]
        force_followup = True
        mode = "ADAPTIVE_FOLLOW_UP"

        # Follow-ups see only this skill's turns, so other topics cannot bleed in (UI7).
    shown_turns = (
        [turn for turn in history_turns if turn.get("target_skill") == target_skill]
        if force_followup
        else history_turns
    )
    shown_history = json.dumps(shown_turns, ensure_ascii=False, indent=2)

    focus_payload = {
        "all_focus_skills": cleaned_focus,
        "unasked_skills": unasked_skills,
    }
    focus_data = json.dumps(focus_payload, ensure_ascii=False, indent=2)
    question_bank = json.dumps(
        load_question_templates(),
        ensure_ascii=False,
        indent=2,
    )

    # Tell the language model which skill and question style to use for this turn.
    prompt = (
        "Generate the next technical interview question for the candidate based on "
        "the supplied data blocks. Set round_type to 'technical'.\n\n"
        "CRITICAL: Do NOT repeat any question text from <interview_history>. "
        "If IS_FOLLOWUP is true, probe deeper into technical trade-offs, internal "
        "mechanics, or edge cases.\n\n"
        "DIRECTIVE:\n"
        f"TARGET_SKILL: {target_skill}\n"
        f"IS_FOLLOWUP: {str(force_followup).lower()}\n"
        f"MODE: {mode}\n\n"
        f"{format_data_context(focus_data, 'technical_focus')}\n\n"
        f"{format_data_context(job_context, 'job_context')}\n\n"
        f"{format_data_context(shown_history, 'interview_history')}\n\n"
        f"{format_data_context(question_bank, 'question_bank')}"
    )
    # Request a schema-checked response, then enforce fields controlled by this agent.
    # Request a schema-checked response, then enforce fields controlled by this agent.
    # Exact and near-identical repeats get one retry (UI7), then raise as before.
    previous_questions = [turn["question_text"] for turn in history_turns]
    for _attempt in range(2):
        question = generate_structured(prompt, SYSTEM_PROMPT, InterviewQuestion)
        result = InterviewQuestion.model_validate(
            {
                **question.model_dump(mode="python"),
                "target_skill_or_gap": target_skill,
                "round_type": "technical",
                "is_followup": force_followup,
            }
        )
        if not _too_similar(result.question_text, previous_questions):
            return result
        prompt += (
            "\n\nYour last question was too similar to an earlier one. "
            "Ask about a different aspect of the skill."
        )
    raise ValueError("The generated technical question repeats a previous question.")


if __name__ == "__main__":
    focus = ["AWS", "Python"]

    # 1. Turn 0: Initial question.
    first_question = generate_technical_question(technical_focus=focus)
    assert first_question.target_skill_or_gap == focus[0]
    assert first_question.is_followup is False
    print("Turn 0 (First Question):", first_question.question_text)

    # 2. Turn 1: A vague answer triggers a new follow-up on the same skill.
    history_vague = [
        {
            "turn_index": 0,
            "question": first_question.model_dump(mode="json"),
            "student_answer": "Lambda runs code in the cloud without servers.",
            "score": None,
        }
    ]
    follow_up = generate_technical_question(
        technical_focus=focus,
        interview_history=history_vague,
    )
    assert follow_up.target_skill_or_gap == "AWS"
    assert follow_up.is_followup is True
    assert follow_up.question_text != first_question.question_text
    print("\nTurn 1 (Adaptive Follow-up on AWS):", follow_up.question_text)

    # 3. Turn 1: Both common pass phrases advance to the next unasked skill.
    for pass_answer in ("I have no idea", "I have no clue"):
        history_pass = [
            {
                "turn_index": 0,
                "question": first_question.model_dump(mode="json"),
                "student_answer": pass_answer,
                "score": None,
            }
        ]
        next_question = generate_technical_question(
            technical_focus=focus,
            interview_history=history_pass,
        )
        assert next_question.target_skill_or_gap == "Python"
        assert next_question.is_followup is False
        print(f"\nAfter pass ({pass_answer}):", next_question.question_text)

    # 4. Turn 2: Answering a follow-up advances rather than looping on AWS.
    history_after_followup = [
        {
            "turn_index": 0,
            "question": first_question.model_dump(mode="json"),
            "student_answer": "Lambda runs code in the cloud without servers.",
            "score": None,
        },
        {
            "turn_index": 1,
            "question": follow_up.model_dump(mode="json"),
            "student_answer": "A cold start occurs while AWS initializes the runtime.",
            "score": None,
        },
    ]
    turn_two = generate_technical_question(
        technical_focus=focus,
        interview_history=history_after_followup,
    )
    assert turn_two.target_skill_or_gap == "Python"
    assert turn_two.is_followup is False
    print("\nTurn 2 (Advanced to Python after follow-up):", turn_two.question_text)
