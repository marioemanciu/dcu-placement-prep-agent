"""Coordinator Agent: runs one session step by step (steps 1-9 in the architecture)."""


class Coordinator:
    def __init__(self):
        self.state = {}  # session memory: job analysis, gaps, plan, transcript, scores

    def run_analysis(self, cv_text: str, job_description: str):
        """Steps 3-5: job analysis -> gap analysis -> planning. Pauses at H1 for confirmation."""
        raise NotImplementedError

    def run_interview(self):
        """Step 6: technical then behavioural interview (H2: student answers)."""
        raise NotImplementedError

    def finish(self, consent_to_save: bool):
        """Steps 7-9: scoring, report, save to memory only if consent given (H3)."""
        raise NotImplementedError
