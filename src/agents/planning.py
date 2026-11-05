"""Planning Agent: ranks gaps and sets the interview focus.

The LLM decides the ranking and the technical/behavioural split. Code then enforces
the hard rules, so invented or rejected gaps can never reach the interview.

"""

import json
from pathlib import Path

from src.llm import format_data_context, generate_structured
from src.schemas import JobAnalysisOutput, PlanningOutput, SkillEvidence

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "planning.md"
MAX_PRIORITY = 5
MAX_FOCUS = 3
DEFAULT_COMPETENCIES = ["Teamwork", "Communication", "Problem solving"]


def run(
    gaps: list[SkillEvidence], job_analysis: JobAnalysisOutput, previous_memory=None
) -> PlanningOutput:
    """Called by the Coordinator as planning_agent(gaps, job_analysis, previous_memory)."""
    # 1. Load the agent's instructions

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")

    # 2a. Candidates: the skill name of each confirmed gap

    candidates = [gap.skill for gap in gaps]
    if not candidates:
        candidates = list(
            job_analysis.likely_topics
        )  # no gaps: practise the role's typical topics

    # 2b. Past weaknesses from long-term memory (memory stores plain strings)

    past_weaknesses = previous_memory.get("weaknesses", []) if previous_memory else []

    # 2c. Build the user prompt from three tagged data blocks

    user_prompt = "\n\n".join(
        [
            format_data_context(json.dumps(candidates), "confirmed_gaps"),
            format_data_context(job_analysis.model_dump_json(), "job_analysis"),
            format_data_context(json.dumps(past_weaknesses), "past_weaknesses"),
        ]
    )

    # 3. Ask the LLM for a plan (llm.py validates the JSON and repairs it once)
    plan = generate_structured(user_prompt, system_prompt, PlanningOutput)

    # 4. Enforce the hard rules in code
    return _enforce_rules(plan, candidates, job_analysis)


def _normalise(text: str) -> str:
    return text.strip().lower()


def _unique(
    items: list[str], allowed: dict[str, str], exclude: set[str], limit: int
) -> list[str]:
    """Keep items found in `allowed` (using its spelling), skip duplicates and excluded items."""
    result: list[str] = []
    seen = set(exclude)
    for item in items:
        key = _normalise(item)
        if key in allowed and key not in seen:
            result.append(allowed[key])
            seen.add(key)
        if len(result) == limit:
            break
    return result


def _enforce_rules(
    plan: PlanningOutput, candidates: list[str], job_analysis: JobAnalysisOutput
) -> PlanningOutput:
    """Rules in code, not trusted to the LLM."""
    gap_names = {_normalise(c): c for c in candidates if c.strip()}

    # Rule 1: priority gaps must be real confirmed gaps (drops invented or H1-rejected ones)

    priority = _unique(plan.priority_gaps, gap_names, set(), MAX_PRIORITY)
    if not priority:  # LLM ranked nothing valid: keep the original order
        priority = list(gap_names.values())[:MAX_PRIORITY]
    priority_names = {_normalise(p): p for p in priority}

    # Rule 2: technical focus may only use priority gaps
    technical = _unique(plan.technical_focus, priority_names, set(), MAX_FOCUS)

    # Rule 3: behavioural focus may use priority gaps or soft skills from the job analysis,
    # never an item already in the technical list
    job_items = job_analysis.required_skills + job_analysis.likely_topics
    behavioural_allowed = {
        **{_normalise(s): s for s in job_items if s.strip()},
        **priority_names,
    }
    technical_keys = {_normalise(t) for t in technical}
    behavioural = _unique(
        plan.behavioural_focus, behavioural_allowed, technical_keys, MAX_FOCUS
    )

    # Rule 4: the behavioural round is never empty
    if not behavioural:
        defaults = {_normalise(d): d for d in DEFAULT_COMPETENCIES}
        behavioural = _unique(DEFAULT_COMPETENCIES, defaults, technical_keys, MAX_FOCUS)

    # Rule 5: the technical round is never empty while there are priority gaps
    if not technical:
        behavioural_keys = {_normalise(b) for b in behavioural}
        technical = _unique(priority, priority_names, behavioural_keys, MAX_FOCUS)

    return PlanningOutput(
        priority_gaps=priority,
        technical_focus=technical,
        behavioural_focus=behavioural,
    )
