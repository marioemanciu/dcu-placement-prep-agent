# DCU Placement Preparation Agent

CSC1202 Project — Group 14 · **Track 2** (Programming and Agent Frameworks)

A multi-agent LLM system that helps DCU students prepare for placement and graduate interviews.
A student uploads their CV and a target job description; specialised agents analyse the role, find
skill gaps, plan practice, run an adaptive technical and STAR behavioural mock interview, score the
answers against a rubric and produce a downloadable prep report.

The LLM runs locally via [Ollama](https://ollama.com), so CVs never leave the machine.

## Architecture

See `docs/architecture.png` (Phase 2 design). A Coordinator manages the specialised agents:

| Agent | File | Role |
|---|---|---|
| Coordinator | `src/coordinator.py` | Runs the session, passes results between agents, pauses at H1 |
| Job-analysis | `src/agents/job_analysis.py` | Extracts required skills, level and topics from the JD |
| Gap-analysis | `src/agents/gap_analysis.py` | Compares requirements with the CV and past weaknesses; evidence is checked against the CV text |
| Planning | `src/agents/planning.py` | Prioritises which gaps to practise (technical vs behavioural) |
| Technical Interviewer | `src/agents/technical_interviewer.py` | Adaptive role-specific questions and follow-ups |
| Behavioural Interviewer | `src/agents/behavioural_interviewer.py` | STAR questions; follows up on missing STAR parts |
| Scoring | `src/agents/scoring.py` | Scores answers against `data/rubric.json`, quoting the student's own words |

Tools: `src/tools/parser.py` (CV → text), `src/tools/report.py` (Word `.docx` report, no LLM).
Memory: `src/memory.py` (weak topics and scores, saved only with the student's consent; never the CV).

**Design principle:** the LLM writes and judges; code decides and enforces (topics, follow-up limits,
rubric criterion, evidence quotes, injection guards). Every agent's output is validated with Pydantic.

**Human checkpoints:**
- **H1** — the student confirms or unticks the detected gaps before the interview.
- **H2** — the student can answer or skip every question.
- **H3** — the student chooses whether to save weak topics for their next session.

## How to run

### 1. Install Ollama and the model
Install Ollama from https://ollama.com, start it, then:
```bash
ollama pull llama3.1:8b
```

### 2. Create a virtual environment and install dependencies (Python 3.10+)
```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash)
# source .venv/bin/activate        # macOS / Linux
pip install -r requirements.txt
```

### 3. Start the app
```bash
streamlit run app.py
```
Then open http://localhost:8501.

### 4. Using the app
1. In the sidebar, leave **Use real agents** on (needs Ollama) and press **Warm up model**
   (the first LLM call takes ~20 s).
2. Pick a **sample CV** and **sample job description**, or upload your own CV (PDF/Word) and paste a JD.
3. **Analyse** → check the strengths and gaps → untick any wrong gap → **Confirm** (H1).
4. **Start mock interview**: a technical round, then a behavioural (STAR) round. Answer or skip (H2).
5. **Get my scores** → **Download report (.docx)** → optionally save weak topics (H3).
6. Run again with the same **Student ID** to see saved weak topics prioritised.

**Stub mode:** turn **Use real agents** off to run the whole flow instantly with simple keyword-based
stand-ins (no Ollama). Useful for UI work and as a demo fallback.

### 5. Run the tests
Unit tests use a fake LLM, so Ollama is not needed:
```bash
python -m pytest tests -q
```
Live tests call the real model (Ollama must be running); results are logged in `tests/test_log.csv`:
```bash
python -m tests.run_planning_live
python -m tests.run_behavioural_live
python -m tests.run_scoring_live
```

## Repository structure

```
app.py                 Streamlit interface (H1–H3, interview loop, scores, report download)
src/                   Coordinator, agents, tools, memory, LLM wrapper, guardrails
src/agents/stubs.py    Offline stand-ins for every agent (stub mode)
prompts/               One prompt file per agent (versioned in Git)
data/                  Rubric, question bank, fictional test CVs and JDs (demo samples)
tests/                 Unit tests (fake LLM), live test scripts and test_log.csv
docs/                  Architecture diagram and design notes
memory_store/          Saved student memory (created at runtime, git-ignored)
```

## Data protection

Only fictional CVs are used for testing. No real personal data is committed to this repository.
Long-term memory stores weak topics and scores only, and only after the student consents.

## Team

Stephen McManus · Niall O'Donoghue · Maksym Sharai · Emir Demirkol · Farah Ahmed · Mario Ciuciu