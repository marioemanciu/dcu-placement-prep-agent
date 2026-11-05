"""Stub agents for building and demoing the UI before the real agents exist.

They follow the same contracts as the real agents (see src/schemas.py and the
Coordinator), so each one can be swapped for the real agent with a one-line change.
They use simple keyword matching, not the LLM. Delete each stub once its agent lands.
"""

from src.schemas import (
    GapAnalysisOutput,
    JobAnalysisOutput,
    PlanningOutput,
    SkillEvidence,
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
