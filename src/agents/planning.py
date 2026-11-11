"""Planning Agent: ranks confirmed gaps and splits them into technical and behavioural focus.

The LLM decides the ranking and the technical/behavioural split. Code then enforces
the hard rules, so invented or rejected gaps can never reach the interview.
"""

import json
from pathlib import Path

from src.guardrails import is_suspicious
from src.llm import format_data_context, generate_structured
from src.schemas import JobAnalysisOutput, PlanningOutput, SkillEvidence

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "planning.md"
MAX_PRIORITY = 5
MAX_FOCUS = 3
MIN_BEHAVIOURAL = 2  # enough topics for more than one STAR question
DEFAULT_COMPETENCIES = ["Teamwork", "Communication", "Problem solving"]

# Word stems that mark a skill as behavioural (soft) rather than technical.
SOFT_SKILL_KEYWORDS = (
    "team",
    "communicat",
    "present",
    "stakeholder",
    "leader",
    "collaborat",
    "problem solving",
    "time management",
    "adapt",
    "client",
    "conflict",
    "customer",
    "interpersonal",
    "negotiat",
    "organis",
    "organiz",
    "project",
)


def run(
    gaps: list[SkillEvidence], job_analysis: JobAnalysisOutput, previous_memory=None
) -> PlanningOutput:
    """Called by the Coordinator as planning_agent(gaps, job_analysis, previous_memory)."""
    # 1. Load the agent's instructions
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")

    # 2a. Candidates: the skill name of each confirmed gap
    # F3: drop gap names that look like injected instructions rather than skills
    candidates = [gap.skill for gap in gaps if not is_suspicious(gap.skill)]
    if not candidates:
        # No gaps: practise the role's typical topics instead
        candidates = job_analysis.likely_topics

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
    return _enforce_rules(plan, candidates, job_analysis, past_weaknesses)


def _normalise(text: str) -> str:
    return text.strip().lower()


def _is_soft(skill: str) -> bool:
    """True if the skill looks like a behavioural competency, e.g. teamwork."""
    name = _normalise(skill)
    return any(keyword in name for keyword in SOFT_SKILL_KEYWORDS)


def _unique(
    items: list[str], allowed: dict[str, str], exclude: set[str], limit: int
) -> list[str]:
    """Keep items found in `allowed` (using its spelling), skip duplicates and excluded items."""
    result: list[str] = []
    seen = set(exclude)
    for item in items:
        if len(result) >= limit:
            break
        key = _normalise(item)
        if key in allowed and key not in seen:
            result.append(allowed[key])
            seen.add(key)
    return result


def _enforce_rules(
    plan: PlanningOutput,
    candidates: list[str],
    job_analysis: JobAnalysisOutput,
    past_weaknesses: list[str] | None = None,
) -> PlanningOutput:
    """Rules in code, not trusted to the LLM."""
    gap_names = {_normalise(c): c for c in candidates if c.strip()}
    past_keys = {_normalise(w) for w in (past_weaknesses or [])}

    # Rule 1: priority gaps must be real confirmed gaps (drops invented or H1-rejected ones)
    priority = _unique(plan.priority_gaps, gap_names, set(), MAX_PRIORITY)

    # Rule 1b (F1): confirmed gaps the LLM left out are added at the end, past weaknesses first
    leftovers = sorted(gap_names.values(), key=lambda g: _normalise(g) not in past_keys)
    already = {_normalise(p) for p in priority}
    priority += _unique(leftovers, gap_names, already, MAX_PRIORITY - len(priority))
    priority_names = {_normalise(p): p for p in priority}

    # Rule 2 (F4): technical focus only uses priority gaps, and never soft skills
    technical = [
        t
        for t in _unique(plan.technical_focus, priority_names, set(), MAX_FOCUS)
        if not _is_soft(t)
    ]

    # Rule 3: behavioural focus may use priority gaps or skills from the job analysis,
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

    # Rule 4 (F2): every priority gap is practised in one round, soft skills in behavioural
    assigned = {_normalise(x) for x in technical + behavioural}
    for gap in priority:
        if _normalise(gap) in assigned:
            continue
        target = behavioural if _is_soft(gap) else technical
        if len(target) < MAX_FOCUS:
            target.append(gap)
            assigned.add(_normalise(gap))

    # Rule 5: the behavioural round has at least MIN_BEHAVIOURAL topics.
    # Top up with soft skills from the job analysis first, then default competencies.
    if len(behavioural) < MIN_BEHAVIOURAL:
        used = {_normalise(x) for x in technical + behavioural}
        soft_job_items = [s for s in job_items if s.strip() and _is_soft(s)]
        top_up = soft_job_items + DEFAULT_COMPETENCIES
        top_up_names = {_normalise(s): s for s in top_up}
        behavioural += _unique(
            top_up, top_up_names, used, MIN_BEHAVIOURAL - len(behavioural)
        )

    return PlanningOutput(
        priority_gaps=priority,
        technical_focus=technical,
        behavioural_focus=behavioural,
    )
