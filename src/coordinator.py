"""Coordinator for the DCU Placement Preparation Agent.

The Coordinator controls execution order, session state, validation,
human checkpoints and hand-offs between specialised agents.
"""

from enum import Enum
from typing import Any, Callable, Type

from pydantic import BaseModel, ValidationError

from src.memory import MemoryStore
from src.schemas import (
    GapAnalysisOutput,
    JobAnalysisOutput,
    PlanningOutput,
    SessionState,
    SkillEvidence,
)


AgentCallable = Callable[..., Any]


class CoordinatorError(RuntimeError):
    """Raised when the session cannot safely continue."""


class SessionStage(str, Enum):
    """Allowed stages in one preparation session."""

    INTAKE = "intake"
    ANALYSIS_RUNNING = "analysis_running"
    H1_PENDING = "h1_pending"
    READY_FOR_INTERVIEW = "ready_for_interview"
    ANALYSIS_REJECTED = "analysis_rejected"
    COMPLETE = "complete"


class Coordinator:
    """Runs specialised agents in the correct order and manages session state."""

    def __init__(
        self,
        job_analysis_agent: AgentCallable | None = None,
        gap_analysis_agent: AgentCallable | None = None,
        planning_agent: AgentCallable | None = None,
        memory_store: MemoryStore | None = None,
    ):
        self.job_analysis_agent = job_analysis_agent
        self.gap_analysis_agent = gap_analysis_agent
        self.planning_agent = planning_agent

        self.memory = memory_store or MemoryStore()

        self.state = SessionState()
        self.stage = SessionStage.INTAKE

        # Context contains temporary information needed during this session.
        # Raw CV text is never written to long-term memory.
        self.context: dict[str, Any] = {}

        # Gaps stay proposed until the student approves them at H1.
        self._proposed_gaps: list[SkillEvidence] = []
        self._student_id: str | None = None

    @staticmethod
    def _validate_text(value: str, field_name: str) -> str:
        """Reject missing or blank required text."""
        if not isinstance(value, str) or not value.strip():
            raise CoordinatorError(f"{field_name} must not be blank.")

        return value.strip()

    @staticmethod
    def _validate_output(
        output: Any,
        schema: Type[BaseModel],
        agent_name: str,
    ) -> BaseModel:
        """Validate one agent result against its required Pydantic schema."""
        try:
            if isinstance(output, schema):
                return output

            return schema.model_validate(output)

        except ValidationError as exc:
            raise CoordinatorError(
                f"{agent_name} returned invalid structured output."
            ) from exc

    def _run_with_retry(
        self,
        agent: AgentCallable | None,
        schema: Type[BaseModel],
        agent_name: str,
        *args: Any,
    ) -> BaseModel:
        """Run an agent and retry once if its structured output is invalid."""
        if agent is None:
            raise CoordinatorError(f"{agent_name} has not been configured.")

        last_error: CoordinatorError | None = None

        for _attempt in range(2):
            output = agent(*args)

            try:
                return self._validate_output(output, schema, agent_name)

            except CoordinatorError as exc:
                last_error = exc

        raise last_error or CoordinatorError(
            f"{agent_name} failed without returning a valid result."
        )

    def run_analysis(
        self,
        cv_text: str,
        job_description: str,
        student_id: str = "anonymous",
    ) -> dict[str, Any]:
        """Run Job Analysis, Gap Analysis and Planning, then pause at H1."""
        if self.stage not in {
            SessionStage.INTAKE,
            SessionStage.ANALYSIS_REJECTED,
        }:
            raise CoordinatorError(
                f"Analysis cannot start while session stage is '{self.stage.value}'."
            )

        cv_text = self._validate_text(cv_text, "CV text")
        job_description = self._validate_text(
            job_description,
            "Job description",
        )
        student_id = self._validate_text(student_id, "Student ID")

        self.stage = SessionStage.ANALYSIS_RUNNING
        self._student_id = student_id

        previous_memory = self.memory.load(student_id)

        self.context = {
            "cv_text": cv_text,
            "job_description": job_description,
            "previous_memory": previous_memory,
        }

        job_analysis = self._run_with_retry(
            self.job_analysis_agent,
            JobAnalysisOutput,
            "Job-analysis Agent",
            job_description,
        )

        self.state = self.state.model_copy(
            update={"job_analysis": job_analysis}
        )

        gap_analysis = self._run_with_retry(
            self.gap_analysis_agent,
            GapAnalysisOutput,
            "Gap-analysis Agent",
            cv_text,
            job_analysis,
            previous_memory,
        )

        self._proposed_gaps = list(gap_analysis.gaps)

        plan = self._run_with_retry(
            self.planning_agent,
            PlanningOutput,
            "Planning Agent",
            self._proposed_gaps,
            job_analysis,
            previous_memory,
        )

        self.state = self.state.model_copy(
            update={"plan": plan}
        )

        self.stage = SessionStage.H1_PENDING

        return {
            "stage": self.stage.value,
            "job_analysis": job_analysis,
            "strengths": gap_analysis.strengths,
            "proposed_gaps": gap_analysis.gaps,
            "plan": plan,
        }

    def confirm_analysis(
        self,
        approved: bool,
        confirmed_gaps: list[SkillEvidence | dict[str, Any]] | None = None,
    ) -> SessionState:
        """H1: approve or reject the analysis before interview preparation."""
        if self.stage != SessionStage.H1_PENDING:
            raise CoordinatorError(
                "H1 confirmation is only available after analysis."
            )

        if not approved:
            self.stage = SessionStage.ANALYSIS_REJECTED
            return self.state

        if confirmed_gaps is None:
            validated_gaps = list(self._proposed_gaps)
        else:
            validated_gaps = []

            for gap in confirmed_gaps:
                if isinstance(gap, SkillEvidence):
                    validated_gaps.append(gap)
                else:
                    validated_gaps.append(
                        SkillEvidence.model_validate(gap)
                    )

        self.state = self.state.model_copy(
            update={"confirmed_gaps": validated_gaps}
        )

        # If the student changed the proposed gaps at H1,
        # rebuild the plan so rejected gaps cannot influence the interview.
        if validated_gaps != self._proposed_gaps:
            updated_plan = self._run_with_retry(
                self.planning_agent,
                PlanningOutput,
                "Planning Agent",
                validated_gaps,
                self.state.job_analysis,
                self.context.get("previous_memory", {}),
            )

            self.state = self.state.model_copy(
                update={"plan": updated_plan}
            )

        self.stage = SessionStage.READY_FOR_INTERVIEW

        return self.state

    def snapshot(self) -> dict[str, Any]:
        """Return a safe view of current execution state without raw CV text."""
        return {
            "stage": self.stage.value,
            "state": self.state.model_dump(),
            "proposed_gaps": [
                gap.model_dump() for gap in self._proposed_gaps
            ],
        }

    def reset_session(self) -> None:
        """Clear current-session state and sensitive temporary context."""
        self.state = SessionState()
        self.stage = SessionStage.INTAKE
        self.context.clear()
        self._proposed_gaps.clear()
        self._student_id = None

    def run_interview(self) -> None:
        """Interview orchestration will be connected when interview agents land."""
        if self.stage != SessionStage.READY_FOR_INTERVIEW:
            raise CoordinatorError(
                "Interview cannot begin before H1 confirmation."
            )

        raise NotImplementedError(
            "Interview agents are not integrated yet."
        )

    def finish(self, consent_to_save: bool) -> None:
        """Final scoring/report integration will be added with remaining agents."""
        raise NotImplementedError(
            "Scoring and report agents are not integrated yet."
        )
