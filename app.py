"""Streamlit chat interface for the DCU Placement Preparation Agent.

Run with:  streamlit run app.py

Streamlit re-runs this whole script on every click, so everything that must survive
between clicks (the Coordinator and its session) lives in st.session_state.
The screen shown is chosen from the Coordinator's current stage.
"""

import streamlit as st

from src.agents import planning
from src.agents.stubs import stub_gap_analysis, stub_job_analysis, stub_planning
from src.coordinator import Coordinator, CoordinatorError, SessionStage
from src.llm import OllamaConnectionError, generate_text
from src.tools.parser import file_to_text

st.set_page_config(page_title="DCU Placement Preparation Agent", page_icon="💼")


# ---------- Setup ----------
def build_coordinator(use_llm: bool) -> Coordinator:
    """Wire the agents into the Coordinator. Swap each stub for the real agent when it lands."""
    return Coordinator(
        job_analysis_agent=stub_job_analysis,  # TODO: real Job-analysis Agent
        gap_analysis_agent=stub_gap_analysis,  # TODO: real Gap-analysis Agent
        planning_agent=planning.run if use_llm else stub_planning,
    )


def start_new_session() -> None:
    st.session_state.coordinator = build_coordinator(st.session_state.use_llm)
    st.session_state.analysis = None
    st.session_state.error = None


if "use_llm" not in st.session_state:
    st.session_state.use_llm = True
if "coordinator" not in st.session_state:
    start_new_session()

coordinator: Coordinator = st.session_state.coordinator


# ---------- Sidebar ----------
with st.sidebar:
    st.header("Settings")
    student_id = st.text_input("Student ID", value="demo_student")
    use_llm = st.toggle(
        "Use real Planning Agent (needs Ollama)",
        value=st.session_state.use_llm,
        help="Off = fast stub agents only, useful when working on the UI.",
    )
    if use_llm != st.session_state.use_llm:
        st.session_state.use_llm = use_llm
        start_new_session()
        st.rerun()

    if st.button(
        "Warm up model", help="The first LLM call is slow; run this before a demo."
    ):
        try:
            with st.spinner("Loading model..."):
                generate_text("Reply with OK.", "You are a test assistant.")
            st.success("Model ready.")
        except OllamaConnectionError:
            st.error("Ollama is not running. Start the Ollama app and try again.")

    if st.button("Start new session"):
        start_new_session()
        st.rerun()

    st.caption(f"Stage: `{coordinator.stage.value}`")


# ---------- Main screen ----------
st.title("💼 DCU Placement Preparation Agent")

if st.session_state.error:
    st.error(st.session_state.error)

stage = coordinator.stage

# ----- Step 1: upload CV and job description -----
if stage in (SessionStage.INTAKE, SessionStage.ANALYSIS_REJECTED):
    if stage == SessionStage.ANALYSIS_REJECTED:
        st.info(
            "Analysis rejected. Upload a different CV or job description to try again."
        )

    st.write("Upload your CV and paste the job description you're applying for.")
    with st.form("intake"):
        cv_file = st.file_uploader("Your CV (PDF or Word)", type=["pdf", "docx"])
        job_description = st.text_area("Job description", height=200)
        submitted = st.form_submit_button("Analyse")

    if submitted:
        st.session_state.error = None
        if cv_file is None or not job_description.strip():
            st.session_state.error = "Please upload a CV and paste a job description."
            st.rerun()
        try:
            cv_text = file_to_text(cv_file)
            with st.spinner("Analysing the role and your CV..."):
                st.session_state.analysis = coordinator.run_analysis(
                    cv_text, job_description, student_id
                )
        except ValueError as error:  # parser: unsupported or empty file
            st.session_state.error = f"Could not read your CV: {error}"
        except OllamaConnectionError:
            st.session_state.error = (
                "Ollama is not running. Start the Ollama app, then start a new session."
            )
        except CoordinatorError as error:
            st.session_state.error = f"Something went wrong: {error}"
        st.rerun()

# ----- An agent crashed part-way (known Coordinator issue) -----
elif stage == SessionStage.ANALYSIS_RUNNING:
    st.warning("The analysis did not finish. Please start a new session.")
    if st.button("Start again"):
        start_new_session()
        st.rerun()

# ----- Step 2: H1, the student confirms the analysis -----
elif stage == SessionStage.H1_PENDING:
    analysis = st.session_state.analysis
    job = analysis["job_analysis"]

    st.subheader("1. The role")
    st.write(f"**Level:** {job.experience_level}")
    st.write("**Required skills:** " + ", ".join(job.required_skills))
    st.write("**Likely interview topics:** " + ", ".join(job.likely_topics))

    st.subheader("2. Your strengths")
    if analysis["strengths"]:
        for item in analysis["strengths"]:
            st.write(f"✅ **{item.skill}**: {item.evidence_cv}")
    else:
        st.write("No clear strengths found for this role.")

    st.subheader("3. Gaps to practise")
    st.caption(
        "Untick any gap that's wrong. Only ticked gaps will be used in your interview."
    )
    selected = []
    for index, gap in enumerate(analysis["proposed_gaps"]):
        if st.checkbox(
            f"**{gap.skill}**: {gap.requirement_jd}", value=True, key=f"gap_{index}"
        ):
            selected.append(gap)

    col_approve, col_reject = st.columns(2)
    if col_approve.button("✅ Confirm and continue", type="primary"):
        with st.spinner("Updating your practice plan..."):
            try:
                coordinator.confirm_analysis(approved=True, confirmed_gaps=selected)
            except (CoordinatorError, OllamaConnectionError) as error:
                st.session_state.error = f"Could not update the plan: {error}"
        st.rerun()
    if col_reject.button("❌ This analysis is wrong"):
        coordinator.confirm_analysis(approved=False)
        st.rerun()

# ----- Step 3: ready for the interview -----
elif stage == SessionStage.READY_FOR_INTERVIEW:
    plan = coordinator.state.plan
    st.success("Analysis confirmed. Here is your practice plan.")
    st.write("**Priority gaps:** " + (", ".join(plan.priority_gaps) or "none"))
    col_tech, col_beh = st.columns(2)
    col_tech.markdown(
        "**Technical round**\n\n" + "\n".join(f"- {t}" for t in plan.technical_focus)
    )
    col_beh.markdown(
        "**Behavioural round (STAR)**\n\n"
        + "\n".join(f"- {b}" for b in plan.behavioural_focus)
    )

    st.divider()
    st.info(
        "🚧 Mock interview coming soon (Technical and Behavioural Interviewer agents)."
    )
