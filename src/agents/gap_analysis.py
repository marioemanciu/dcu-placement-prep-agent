# Gap Analysis Agent - Compare a candidate's CV with role requirements and prior weaknesses.
#
# Created by    : Maksym Sharai
# Date          : 11/11/2026


import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

if __package__ in (None, ""):
    # Allow `python src\agents\gap_analysis.py` from a checkout, not just `-m`.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.llm import format_data_context, generate_structured
from src.schemas import GapAnalysisOutput, JobAnalysisOutput, PersistentWeakness

# Resolve from this file so loading the prompt does not depend on the caller's cwd.
SYSTEM_PROMPT = (
    Path(__file__).resolve().parents[2] / "prompts" / "gap_analysis.md"
).read_text(encoding="utf-8")


def _memory_records(
    previous_memory: (
        list[PersistentWeakness] | list[dict[str, Any]] | dict[str, Any] | None
    ),
) -> list[dict[str, Any]]:
    """Extract weakness records from supported memory representations."""
    if previous_memory is None:
        return []

    def as_record(value: Any) -> list[dict[str, Any]]:
        # Memory may arrive as schema objects, lists, wrapper dictionaries, or
        # maps keyed by skill name; normalize these shapes before prompting.
        if isinstance(value, PersistentWeakness):
            return [value.model_dump()]
        if isinstance(value, dict):
            if "skill" in value:
                return [value]
            for key in ("weaknesses", "persistent_weaknesses", "past_weaknesses"):
                if key in value:
                    return as_record(value[key])
            if "last_score" in value or "notes" in value:
                return []
            # Also accept memories keyed by skill name, such as {"Python": {...}}.
            records: list[dict[str, Any]] = []
            for skill, details in value.items():
                if isinstance(details, dict):
                    records.extend(as_record({"skill": skill, **details}))
                elif isinstance(details, str):
                    records.append({"skill": skill, "notes": details})
            return records
        if isinstance(value, list):
            records = []
            for item in value:
                records.extend(as_record(item))
            return records
        return []

    return as_record(previous_memory)


def _format_previous_memory(
    previous_memory: (
        list[PersistentWeakness] | list[dict[str, Any]] | dict[str, Any] | None
    ),
) -> str:
    """Create a concise, readable summary of historical weaknesses."""
    summaries = []
    for record in _memory_records(previous_memory):
        skill = record.get("skill")
        if not isinstance(skill, str) or not skill.strip():
            continue

        details = [f"Skill: {skill.strip()}"]
        score = record.get("last_score")
        if score is not None:
            details.append(f"last score: {score}")
        notes = record.get("notes")
        if isinstance(notes, str) and notes.strip():
            details.append(f"notes: {notes.strip()}")
        summaries.append("; ".join(details))

    return "\n".join(summaries) if summaries else "No prior weaknesses recorded."


def analyze_gaps(
    cv_text: str,
    job_analysis: JobAnalysisOutput | dict[str, Any],
    previous_memory: (
        list[PersistentWeakness] | list[dict[str, Any]] | dict[str, Any] | None
    ) = None,
) -> GapAnalysisOutput:
    """Identify CV-supported strengths and evidence-based skill gaps."""
    if isinstance(job_analysis, dict):
        # Validate dict inputs before serializing them as the requirement source.
        job_analysis = JobAnalysisOutput.model_validate(job_analysis)
    elif not isinstance(job_analysis, JobAnalysisOutput):
        raise TypeError("job_analysis must be a JobAnalysisOutput or dictionary")

    # Keep raw CV, requirements, and memory inside passive-data tags so embedded
    # instructions are not confused with the trusted system prompt.
    cv_context = format_data_context(cv_text, "cv_data")
    requirements_json = json.dumps(
        job_analysis.model_dump(),
        ensure_ascii=False,
        indent=2,
    )
    requirements_context = format_data_context(
        requirements_json,
        "job_requirements",
    )
    memory_context = format_data_context(
        _format_previous_memory(previous_memory),
        "past_weaknesses",
    )
    prompt = (
        "Compare the candidate's CV with the extracted job requirements and "
        "relevant historical weaknesses below.\n\n"
        f"{cv_context}\n\n"
        f"{requirements_context}\n\n"
        f"{memory_context}\n\n"
        # Use extracted required_skills as the only source of requirements;
        # likely_topics provide context but must not expand the assessed set.
        "Assess each entry in required_skills. Use the exact applicable "
        "requirement text in requirement_jd, and cite CV evidence verbatim. "
        "Use evidence_cv=\"None\" when the CV contains no relevant evidence. "
        "Likely topics may help interpret the role, but are not additional "
        "requirements unless they appear in required_skills."
    )

    return generate_structured(prompt, SYSTEM_PROMPT, GapAnalysisOutput)


def gap_analysis_agent(
    cv_text: str,
    job_analysis: JobAnalysisOutput | dict[str, Any],
    previous_memory: (
        list[PersistentWeakness] | list[dict[str, Any]] | dict[str, Any] | None
    ) = None,
) -> GapAnalysisOutput:
    """Coordinator-facing name for :func:`analyze_gaps`."""
    return analyze_gaps(cv_text, job_analysis, previous_memory)


if __name__ == "__main__":
    mock_cv = (
        "Maksym Sharai\n"
        "Experience:\n"
        "- Backend developer using Python (FastAPI), C, and PostgreSQL.\n"
        "- Designed REST APIs and relational schemas.\n"
    )
    mock_job = JobAnalysisOutput(
        required_skills=["Python", "PostgreSQL", "Docker", "AWS DynamoDB"],
        experience_level="Intern",
        likely_topics=["Database Design", "Cloud Infrastructure"],
    )
    mock_memory = [
        PersistentWeakness(skill="Docker", last_score=2, notes="Struggled with multi-stage builds.")
    ]

    print("--- Running Gap Analysis (Mock Verification) ---")
    try:
        result = analyze_gaps(mock_cv, mock_job, mock_memory)
        print("\n[Strengths Found]:")
        for s in result.strengths:
            print(f"  + {s.skill}: {s.evidence_cv}")
        print("\n[Gaps Found]:")
        for g in result.gaps:
            print(f"  - {g.skill} (JD: {g.requirement_jd}): {g.evidence_cv}")
    except Exception as exc:
        print(f"Execution failed (ensure Ollama is running if testing live): {exc}")
