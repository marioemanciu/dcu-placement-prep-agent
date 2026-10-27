# DCU Placement Preparation Agent

CSC1202 Project — Group 14 · **Track 2** (Programming and Agent Frameworks)

A multi-agent LLM system that helps DCU students prepare for placement and graduate interviews.
A student uploads their CV and a target job description; specialised agents analyse the role, find
skill gaps, plan practice, run an adaptive technical and STAR behavioural mock interview, score the
answers against a rubric and produce a downloadable prep report.

The LLM runs locally via [Ollama](https://ollama.com), so CVs never leave the machine.

## Architecture

See `docs/architecture.png` (Phase 2 design). A Coordinator Agent manages six specialised agents:

| Agent | File | Role |
|---|---|---|
| Coordinator | `src/coordinator.py` | Runs the session, passes results between agents, pauses at H1–H3 |
| Job-analysis | `src/agents/job_analysis.py` | Extracts required skills, level and topics from the JD |
| Gap-analysis | `src/agents/gap_analysis.py` | Compares requirements with the CV and past weaknesses |
| Planning | `src/agents/planning.py` | Prioritises which gaps to practise |
| Technical Interviewer | `src/agents/technical_interviewer.py` | Adaptive role-specific questions |
| Behavioural Interviewer | `src/agents/behavioural_interviewer.py` | STAR questions and follow-ups |
| Scoring | `src/agents/scoring.py` | Scores answers against `data/rubric.json` with evidence |

Tools: `src/tools/parser.py` (CV/JD → text), `src/tools/report.py` (Word/PDF report).
Memory: `src/memory.py` (session + long-term, saved only with consent).

## Setup

```bash
# 1. Install Ollama and pull a model
ollama pull llama3.1:8b

# 2. Install Python dependencies (Python 3.10+)
pip install -r requirements.txt

# 3. Run the app
streamlit run app.py
```

## Repository structure

```
app.py                 Streamlit chat interface
src/                   Coordinator, agents, tools, memory, LLM wrapper
prompts/               One prompt file per agent (versioned in Git)
data/                  Rubric, question bank, fictional test CVs and JDs
tests/                 Test cases and test log (Round 1 / Round 2)
docs/                  Architecture diagram and design notes
```

## Data protection

Only fictional CVs are used for testing. No real personal data is committed to this repository.

## Team

Stephen McManus · Niall O'Donoghue · Maksym Sharai · Emir Demirkol · Farah Ahmed · Mario Ciuciu
