# Gap Analysis Agent - Compare a candidate's CV with role requirements and prior weaknesses.
#
# Created by    : Maksym Sharai
# Date          : 11/11/2026
# Edited by : Mario Ciuciu
# Date : 17/11/2026

import json
import re
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch


if __package__ in (None, ""):
    # Allow `python src\agents\gap_analysis.py` from a checkout, not just `-m`.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.llm import format_data_context, generate_structured
from src.schemas import GapAnalysisOutput, JobAnalysisOutput, PersistentWeakness, SkillEvidence

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


# ---------- CV grounding (added by Mario Ciuciu, 17/11/2026, after UI5 live testing) ----------
# The LLM sometimes cited evidence that is not in the CV (e.g. "FastAPI" for a Flask CV)
# and marked skills the CV clearly names as gaps. Code now checks every claim against
# the CV text, the same way the Scoring Agent checks its quotes.
NO_EVIDENCE = "None"
MAX_EVIDENCE_WORDS = 25


def _normalise(text: str) -> str:
    """Lowercase, straighten quotes and collapse spaces, so small copy differences still match."""
    text = (
        text.lower()
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    return re.sub(r"\s+", " ", text).strip(" \"'.,;:!?-")


def _in_cv(evidence: str, cv_text: str) -> bool:
    """True if the evidence really appears in the CV (ignoring case, spacing, outer punctuation)."""
    quote = _normalise(evidence)
    return bool(quote) and quote != "none" and quote in _normalise(cv_text)


def _cv_line_naming(skill: str, cv_text: str) -> str | None:
    """The first CV line or sentence that names the skill as a whole word, shortened."""
    flags = (
        0 if len(skill.strip()) <= 2 else re.IGNORECASE
    )  # "C", "R", "Go" must match case
    pattern = re.compile(rf"(?<![\w+#]){re.escape(skill.strip())}(?![\w+#])", flags)
    for line in re.split(r"[\n\r]+|(?<=[.!?])\s+", cv_text):
        line = line.strip(" -\u2022\t")
        if line and pattern.search(line):
            words = line.split()
            return " ".join(words[:MAX_EVIDENCE_WORDS]) + (
                " ..." if len(words) > MAX_EVIDENCE_WORDS else ""
            )
    return None


def _ground_in_cv(
    result: GapAnalysisOutput, cv_text: str, required_skills: list[str] | None = None
) -> GapAnalysisOutput:
    """Keep only CV-backed strengths; move skills the CV clearly names out of the gaps;
    make sure every required skill ends up in one of the two lists."""
    strengths: list[SkillEvidence] = []
    gaps: list[SkillEvidence] = []

    for item in result.strengths:
        if _in_cv(item.evidence_cv, cv_text):
            strengths.append(item)
        elif line := _cv_line_naming(item.skill, cv_text):
            strengths.append(
                item.model_copy(update={"evidence_cv": line})
            )  # real quote instead
        else:
            gaps.append(
                item.model_copy(update={"evidence_cv": NO_EVIDENCE})
            )  # unsupported claim

    for item in result.gaps:
        if line := _cv_line_naming(item.skill, cv_text):
            strengths.append(
                item.model_copy(update={"evidence_cv": line})
            )  # CV names this skill
        elif item.evidence_cv != NO_EVIDENCE and not _in_cv(item.evidence_cv, cv_text):
            gaps.append(item.model_copy(update={"evidence_cv": NO_EVIDENCE}))
        else:
            gaps.append(item)

    # A required skill the LLM left out entirely (UI6: Git) is assessed by code.
    covered = {_normalise(i.skill) for i in strengths + gaps}
    for skill in required_skills or []:
        if not skill.strip() or _normalise(skill) in covered:
            continue
        line = _cv_line_naming(skill, cv_text)
        missing = SkillEvidence(
            skill=skill,
            requirement_jd=f"Required skill: {skill}",
            evidence_cv=line or NO_EVIDENCE,
        )
        (strengths if line else gaps).append(missing)
        covered.add(_normalise(skill))

    strong = {_normalise(s.skill) for s in strengths}
    gaps = [g for g in gaps if _normalise(g.skill) not in strong]  # never in both lists
    return GapAnalysisOutput(strengths=strengths, gaps=gaps)


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
        'Use evidence_cv="None" when the CV contains no relevant evidence. '
        "Likely topics may help interpret the role, but are not additional "
        "requirements unless they appear in required_skills."
    )

    result = generate_structured(prompt, SYSTEM_PROMPT, GapAnalysisOutput)
    return _ground_in_cv(
        result, cv_text, job_analysis.required_skills
    )  # code checks every evidence claim against the CV


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
        PersistentWeakness(
            skill="Docker", last_score=2, notes="Struggled with multi-stage builds."
        )
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
