"""Streamlit chat interface for the DCU Placement Preparation Agent.

Run with:  streamlit run app.py

Streamlit re-runs this whole script on every click, so everything that must survive
between clicks (the Coordinator and its session) lives in st.session_state.
The screen shown is chosen from the Coordinator's current stage.
"""

import streamlit as st
from pathlib import Path
from io import BytesIO

from src.agents import planning
from src.agents.behavioural_interviewer import generate_behavioural_question
from src.agents.gap_analysis import gap_analysis_agent
from src.agents.job_analysis import job_analysis_agent
from src.agents.stubs import (
    stub_behavioural_question,
    stub_gap_analysis,
    stub_job_analysis,
    stub_planning,
    stub_technical_question,
)
from src.agents.technical_interviewer import generate_technical_question
from src.coordinator import Coordinator, CoordinatorError, SessionStage
from src.llm import OllamaConnectionError, generate_text
from src.schemas import InterviewTurn
from src.tools.parser import file_to_text

st.set_page_config(page_title="DCU Placement Preparation Agent", page_icon="💼")


# ---------- Setup ----------
ROUNDS = ("technical", "behavioural")
MAX_PER_ROUND = 6  # cap so a demo interview stays short
SKIP = "skip"  # stored for skipped answers (schemas reject blank strings); never followed up
SAMPLE_JDS = Path(__file__).parent / "data" / "test_jds"  # demo job descriptions
SAMPLE_CVS = Path(__file__).parent / "data" / "test_cvs"  # demo CVs (fictional)


def build_coordinator(use_llm: bool) -> Coordinator:
    """Wire the agents into the Coordinator: real agents, or fast stubs for UI work."""
    if use_llm:
        return Coordinator(
            job_analysis_agent=job_analysis_agent,
            gap_analysis_agent=gap_analysis_agent,
            planning_agent=planning.run,
        )
    return Coordinator(
        job_analysis_agent=stub_job_analysis,
        gap_analysis_agent=stub_gap_analysis,
        planning_agent=stub_planning,
    )


def interviewers(use_llm: bool) -> dict:
    if use_llm:
        return {
            "technical": generate_technical_question,
            "behavioural": generate_behavioural_question,
        }
    return {
        "technical": stub_technical_question,
        "behavioural": stub_behavioural_question,
    }


def start_new_session() -> None:
    st.session_state.coordinator = build_coordinator(st.session_state.use_llm)
    st.session_state.analysis = None
    st.session_state.interview = None
    st.session_state.error = None


def next_question(interview: dict) -> None:
    """Get the next question from the current round's interviewer, or move to the next round.

    The UI decides when a round ends (2 x focus topics, max MAX_PER_ROUND); the interviewers decide the topic
    and whether to follow up.
    """
    plan = st.session_state.coordinator.state.plan
    focus = {"technical": plan.technical_focus, "behavioural": plan.behavioural_focus}
    while interview["round_index"] < len(ROUNDS):
        round_type = ROUNDS[interview["round_index"]]
        asked = sum(
            1 for t in interview["history"] if t.question.round_type == round_type
        )
        limit = min(
            MAX_PER_ROUND, 2 * len(focus[round_type])
        )  # one follow-up per topic
        if focus[round_type] and asked < limit:
            agent = interviewers(st.session_state.use_llm)[round_type]
            interview["question"] = agent(
                focus[round_type],
                st.session_state.coordinator.state.job_analysis,
                interview["history"],
            )
            return
        interview["round_index"] += 1
    interview["question"] = None  # both rounds finished


def label(question) -> str:
    text = f"{question.round_type.title()} round · {question.target_skill_or_gap}"
    return text + " · follow-up" if question.is_followup else text


def show_interview(interview: dict) -> None:
    """Chat view: past turns, then the current question with Answer / Skip (H2)."""
    for turn in interview["history"]:
        with st.chat_message("assistant"):
            st.caption(label(turn.question))
            st.write(turn.question.question_text)
        with st.chat_message("user"):
            st.write(
                "_(skipped)_" if turn.student_answer == SKIP else turn.student_answer
            )

    question = interview["question"]
    if question is None:
        st.success("Interview complete! Scoring and your report come next.")
        return

    with st.chat_message("assistant"):
        st.caption(label(question))
        st.write(question.question_text)

    with st.form(f"answer_{len(interview['history'])}", clear_on_submit=True):
        answer = st.text_area("Your answer", height=150)
        col_send, col_skip = st.columns(2)
        send = col_send.form_submit_button("Send answer", type="primary")
        skip = col_skip.form_submit_button("Skip question")

    if send and not answer.strip():
        st.session_state.error = "Write an answer, or press Skip."
        st.rerun()
    if send or skip:
        st.session_state.error = None
        interview["history"].append(
            InterviewTurn(
                turn_index=len(interview["history"]),
                question=question,
                student_answer=answer.strip() if send else SKIP,
            )
        )
        try:
            with st.spinner("Thinking about your answer..."):
                next_question(interview)
        except (ValueError, OllamaConnectionError) as error:
            interview["history"].pop()  # undo, so the student can resend
            st.session_state.error = (
                f"Could not get the next question ({error}). Please send again."
            )
        st.rerun()


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
        "Use real agents (needs Ollama)",
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
    cv_samples = sorted(SAMPLE_CVS.glob("*.docx"))
    cv_names = ["Upload my own"] + [
        p.stem.replace("test_cv_", "").replace("_", " ").title() for p in cv_samples
    ]
    cv_choice = st.selectbox("Sample CV (optional)", cv_names)
    samples = sorted(SAMPLE_JDS.glob("*.txt"))
    names = ["Paste my own"] + [p.stem.replace("_", " ").title() for p in samples]
    choice = st.selectbox("Sample job description (optional)", names)
    sample_text = (
        ""
        if choice == names[0]
        else samples[names.index(choice) - 1].read_text(encoding="utf-8")
    )
    with st.form("intake"):
        cv_file = st.file_uploader("Your CV (PDF or Word)", type=["pdf", "docx"])
        job_description = st.text_area("Job description", value=sample_text, height=200)
        submitted = st.form_submit_button("Analyse")

    if submitted:
        st.session_state.error = None
        if cv_file is None and cv_choice != cv_names[0]:  # an upload wins over a sample
            path = cv_samples[cv_names.index(cv_choice) - 1]
            cv_file = BytesIO(path.read_bytes())
            cv_file.name = path.name  # looks like an uploaded file to the parser
        if cv_file is None or not job_description.strip():
            st.session_state.error = (
                "Please upload or pick a CV, and add a job description."
            )
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
    st.subheader("Mock interview")
    interview = st.session_state.interview
    if interview is None:
        st.write(
            "A technical round, then a behavioural (STAR) round: one question per focus "
            "topic, plus follow-ups. You can skip any question."
        )
        if st.button("🎤 Start mock interview", type="primary"):
            new_interview = {"round_index": 0, "history": [], "question": None}
            try:
                with st.spinner("Preparing your first question..."):
                    next_question(new_interview)
                st.session_state.interview = new_interview
            except (ValueError, OllamaConnectionError) as error:
                st.session_state.error = f"Could not start the interview: {error}"
            st.rerun()
    else:
        show_interview(interview)
