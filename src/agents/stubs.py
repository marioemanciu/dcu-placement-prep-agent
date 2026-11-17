"""Stub agents for building and demoing the UI before the real agents exist.

They follow the same contracts as the real agents (see src/schemas.py and the
Coordinator), so each one can be swapped for the real agent with a one-line change.
They use simple keyword matching, not the LLM. Kept as an offline fallback for UI work and the demo.
"""

from src.schemas import (
    GapAnalysisOutput,
    InterviewQuestion,
    JobAnalysisOutput,
    PlanningOutput,
    SkillEvidence,
    ScoreOutput,
)

# A small vocabulary of skills the stub looks for in the job description.
KNOWN_SKILLS = [
    "Python",
    "Java",
    "JavaScript",
    "SQL",
    "Docker",
    "Git",
    "AWS",
    "Linux",
    "React",
    "Machine learning",
    "Excel",
    "Testing",
    "REST APIs",
    "Teamwork",
    "Communication",
    "Problem solving",
    "Leadership",
    "Time management",
]


def stub_job_analysis(job_description: str) -> JobAnalysisOutput:
    """STUB Job-analysis Agent: finds known skill names in the JD text."""
    text = job_description.lower()
    skills = [skill for skill in KNOWN_SKILLS if skill.lower() in text] or [
        "Communication"
    ]

    if "intern" in text:
        level = "Intern"
    elif "graduate" in text:
        level = "Graduate"
    else:
        level = "Junior"

    return JobAnalysisOutput(
        required_skills=skills,
        experience_level=level,
        likely_topics=skills[:3],
    )


def stub_gap_analysis(
    cv_text: str, job_analysis: JobAnalysisOutput, previous_memory
) -> GapAnalysisOutput:
    """STUB Gap-analysis Agent: a skill is a strength if the CV mentions it, otherwise a gap."""
    cv_lower = cv_text.lower()
    strengths, gaps = [], []

    for skill in job_analysis.required_skills:
        evidence = SkillEvidence(
            skill=skill,
            requirement_jd=f"Job description asks for {skill}",
            evidence_cv=f"CV mentions {skill}" if skill.lower() in cv_lower else "None",
        )
        (strengths if skill.lower() in cv_lower else gaps).append(evidence)

    return GapAnalysisOutput(strengths=strengths, gaps=gaps)


def stub_planning(gaps, job_analysis, previous_memory) -> PlanningOutput:
    """STUB Planning Agent, for running the UI without Ollama."""
    names = [gap.skill for gap in gaps][:5] or list(job_analysis.likely_topics)[:5]
    return PlanningOutput(
        priority_gaps=names,
        technical_focus=names[:3],
        behavioural_focus=["Teamwork", "Communication"],
    )


def _stub_question(focus, history, round_type, template):
    """Cycle through the focus topics; numbered so no question repeats."""
    asked = [t for t in (history or []) if t.question.round_type == round_type]
    topic = focus[len(asked) % len(focus)]
    return InterviewQuestion(
        question_text=f"{template.format(topic=topic)} (Q{len(asked) + 1})",
        target_skill_or_gap=topic,
        round_type=round_type,
        is_followup=False,
    )


def stub_technical_question(technical_focus, job_analysis=None, interview_history=None):
    return _stub_question(technical_focus, interview_history, "technical",
                          "Explain how you have used {topic} in a project.")


def stub_behavioural_question(behavioural_focus, job_analysis=None, interview_history=None):
    return _stub_question(behavioural_focus, interview_history, "behavioural",
                          "Tell me about a time you showed {topic}.")

def stub_score_interview(history, job_analysis=None):
    """STUB Scoring Agent: longer answers score higher. Offline UI work and demo backup only."""
    scored = []
    for turn in history:
        answer = turn.student_answer.strip()
        score = None
        if answer.lower() != "skip":
            score = ScoreOutput(
                score=min(5, 1 + len(answer.split()) // 15),
                rubric_criterion=(
                    "Technical accuracy" if turn.question.round_type == "technical"
                    else "Structure (STAR)"
                ),
                evidence_quote=" ".join(answer.split()[:12]),
                actionable_feedback="Stub feedback: add a concrete example and its outcome.",
            )
        scored.append(turn.model_copy(update={"score": score}))
    return scored