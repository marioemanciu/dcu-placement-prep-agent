# schemas.py
# Pydantic schemas for CV/JD analysis and interview preparation
#
# Created by: Maksym Sharai
# Date: 03/11/2026

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SchemaModel(BaseModel):
    """Base configuration shared by all coordinator-facing schemas."""

    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def reject_blank_strings(cls, value: object) -> object:
        """Reject blank strings while leaving non-string values unchanged."""
        if isinstance(value, str) and not value.strip():
            raise ValueError("Text fields must not be blank.")
        return value


class JobAnalysisOutput(SchemaModel):
    """Structured requirements and likely interview topics extracted from a JD."""

    required_skills: list[str] = Field(
        description="Technical and behavioural requirements extracted from the job description.",
    )
    experience_level: str = Field(
        description='Role level, such as "Intern", "Graduate", or "Junior".',
    )
    likely_topics: list[str] = Field(
        description="Predicted interview domains and topics relevant to the role.",
    )


class SkillEvidence(SchemaModel):
    """Evidence connecting one job requirement to the candidate's CV."""

    skill: str = Field(description="Name of the skill or domain.")
    requirement_jd: str = Field(
        description="Requirement context or a quote from the job description.",
    )
    evidence_cv: str = Field(
        description='Verbatim CV quote or project proof; use "None" when missing.',
    )


class GapAnalysisOutput(SchemaModel):
    """Strengths and gaps identified by comparing a CV with a job description."""

    strengths: list[SkillEvidence] = Field(
        description="Requirements that are well evidenced in the CV.",
    )
    gaps: list[SkillEvidence] = Field(
        description="Requirements that are missing or weakly evidenced in the CV.",
    )


class PlanningOutput(SchemaModel):
    """Practice plan selected for the current preparation session."""

    priority_gaps: list[str] = Field(
        description="Gaps ranked for practice during the current session.",
    )
    technical_focus: list[str] = Field(
        description="Skills selected for technical interview questions.",
    )
    behavioural_focus: list[str] = Field(
        description="Competencies selected for STAR behavioural questions.",
    )


class InterviewQuestion(SchemaModel):
    """A technical or behavioural question presented to the candidate."""

    question_text: str = Field(description="The question asked to the candidate.")
    target_skill_or_gap: str = Field(
        description="Skill, gap, or missing STAR element targeted by the question.",
    )
    round_type: Literal["technical", "behavioural"] = Field(
        description='Interview round type: exactly "technical" or "behavioural".',
    )
    is_followup: bool = Field(
        description="Whether the question probes the candidate's previous response.",
    )


class ScoreOutput(SchemaModel):
    """Rubric-based assessment of one candidate answer."""

    score: int = Field(
        ge=1,
        le=5,
        description="Score on the rubric's five-point scale, from 1 to 5.",
    )
    rubric_criterion: str = Field(
        description="Rubric descriptor matching the configured rubric.",
    )
    evidence_quote: str = Field(
        description="Direct quote from the student's answer supporting the score.",
    )
    actionable_feedback: str = Field(
        description="Concrete advice for improving the answer.",
    )


class InterviewTurn(SchemaModel):
    """One question-and-answer exchange in the interview history."""

    turn_index: int = Field(description="Zero-based position of this turn in the session.")
    question: InterviewQuestion = Field(description="Question presented in this turn.")
    student_answer: str = Field(description="The student's answer to the question.")
    score: Optional[ScoreOutput] = Field(
        default=None,
        description="Rubric score for the answer, when scoring has been completed.",
    )


class SessionState(SchemaModel):
    """Coordinator state carried through analysis, planning, and interviewing."""

    job_analysis: Optional[JobAnalysisOutput] = Field(
        default=None,
        description="Job analysis result, when the JD analysis step is complete.",
    )
    confirmed_gaps: list[SkillEvidence] = Field(
        default_factory=list,
        description="Gaps confirmed at the session checkpoint.",
    )
    plan: Optional[PlanningOutput] = Field(
        default=None,
        description="Practice plan, when planning is complete.",
    )
    interview_history: list[InterviewTurn] = Field(
        default_factory=list,
        description="Questions, answers, and scores recorded during the session.",
    )


class PersistentWeakness(SchemaModel):
    """A concise weakness retained between sessions without raw personal data."""

    skill: str = Field(description="Skill or domain associated with the weakness.")
    last_score: int = Field(description="Most recent score recorded for this weakness.")
    notes: str = Field(description="Actionable notes about the recurring weakness.")