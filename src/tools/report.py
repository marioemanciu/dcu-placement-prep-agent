"""Report Generator tool: builds the Word/PDF prep report from session results.
Date          : 16/11/2026

No LLM is used here. The report only rearranges what the agents already produced
(job analysis, gaps confirmed at H1, plan, scored interview), so it cannot invent
anything. Raw CV text is never included; only the short evidence lines are.
"""

from io import BytesIO

from docx import Document
from docx.shared import Pt

from src.schemas import InterviewTurn, JobAnalysisOutput, PlanningOutput, SkillEvidence

SKIP = "skip"  # how the UI stores a skipped answer
WEAK_SCORE = 2  # topics scoring this or lower go in "What to work on next"
ROUND_TITLES = {
    "technical": "Technical round",
    "behavioural": "Behavioural round (STAR)",
}


def round_average(history: list[InterviewTurn], round_type: str) -> float | None:
    """Average score for one round, ignoring unscored (e.g. skipped) answers."""
    scores = [
        t.score.score
        for t in history
        if t.question.round_type == round_type and t.score
    ]
    return round(sum(scores) / len(scores), 1) if scores else None


def weak_topics(history: list[InterviewTurn]) -> list[str]:
    """Topics with a score of WEAK_SCORE or lower, or that were skipped, in interview order."""
    topics: list[str] = []
    for turn in history:
        skipped = turn.student_answer.strip().lower() == SKIP
        weak = turn.score is not None and turn.score.score <= WEAK_SCORE
        topic = turn.question.target_skill_or_gap
        if (skipped or weak) and topic not in topics:
            topics.append(topic)
    return topics


def _bullets(document, items: list[str], empty: str) -> None:
    for item in items or [empty]:
        document.add_paragraph(item, style="List Bullet")


def _add_turn(document, number: int, turn: InterviewTurn) -> None:
    question = turn.question
    label = f"Q{number}. {question.target_skill_or_gap}"
    if question.is_followup:
        label += " (follow-up)"
    document.add_heading(label, level=3)
    document.add_paragraph(question.question_text)

    skipped = turn.student_answer.strip().lower() == SKIP
    answer = document.add_paragraph()
    answer.add_run("Your answer: ").bold = True
    answer.add_run("(skipped)" if skipped else turn.student_answer)

    if turn.score is None:
        document.add_paragraph(
            "Not scored." if not skipped else "Skipped answers are not scored."
        )
        return
    score = turn.score
    result = document.add_paragraph()
    result.add_run(f"Score: {score.score}/5").bold = True
    result.add_run(f"  ({score.rubric_criterion})")
    quote = document.add_paragraph()
    quote.add_run("Evidence: ").bold = True
    quote.add_run(f"\u201c{score.evidence_quote}\u201d")
    feedback = document.add_paragraph()
    feedback.add_run("How to improve: ").bold = True
    feedback.add_run(score.actionable_feedback)


def build_report(
    job_analysis: JobAnalysisOutput,
    strengths: list[SkillEvidence],
    confirmed_gaps: list[SkillEvidence],
    plan: PlanningOutput,
    history: list[InterviewTurn],
    student_id: str = "student",
) -> bytes:
    """Build the session report as a .docx file and return its bytes (for a download button)."""
    document = Document()
    document.styles["Normal"].font.size = Pt(11)

    document.add_heading("Placement Interview Preparation Report", level=0)
    document.add_paragraph(f"Student: {student_id}")

    document.add_heading("1. The role", level=1)
    document.add_paragraph(f"Level: {job_analysis.experience_level}")
    document.add_paragraph(
        "Required skills: " + (", ".join(job_analysis.required_skills) or "none")
    )

    document.add_heading("2. Your strengths", level=1)
    _bullets(
        document,
        [f"{s.skill}: {s.evidence_cv}" for s in strengths],
        "No clear strengths found.",
    )

    document.add_heading("3. Gaps you practised", level=1)
    _bullets(
        document,
        [f"{g.skill}: {g.requirement_jd}" for g in confirmed_gaps],
        "No gaps confirmed.",
    )

    document.add_heading("4. Practice plan", level=1)
    document.add_paragraph(
        "Technical focus: " + (", ".join(plan.technical_focus) or "none")
    )
    document.add_paragraph(
        "Behavioural focus: " + (", ".join(plan.behavioural_focus) or "none")
    )

    document.add_heading("5. Interview results", level=1)
    if not history:
        document.add_paragraph("No interview was completed in this session.")
    number = 0
    for round_type, title in ROUND_TITLES.items():
        turns = [t for t in history if t.question.round_type == round_type]
        if not turns:
            continue
        average = round_average(history, round_type)
        document.add_heading(
            (
                f"{title}: average {average}/5"
                if average is not None
                else f"{title}: not scored"
            ),
            level=2,
        )
        for turn in sorted(turns, key=lambda t: t.turn_index):
            number += 1
            _add_turn(document, number, turn)

    document.add_heading("6. What to work on next", level=1)
    _bullets(
        document,
        [f"Practise {topic}" for topic in weak_topics(history)],
        "No weak areas found. Keep practising with harder questions.",
    )

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


report_generator_agent = build_report
