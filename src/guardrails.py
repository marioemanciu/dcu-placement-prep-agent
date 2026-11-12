"""Shared guardrails used by every agent (part of the agent harness).

Keeping these checks in one module means all agents filter untrusted text the
same way, and the word list can be extended in one place.
"""

# Words that should never appear in a skill or topic name; they suggest that
# instructions were injected into the CV or job description.
# "system" and "prompt" are deliberately NOT listed: "System design" and
# "Prompt engineering" are real skills and must not be filtered out.
SUSPICIOUS_WORDS = {
    "ignore", "instruction", "instructions", "disregard",
    "override", "jailbreak", "pretend", "forget",
}
MAX_SKILL_WORDS = 6


def is_suspicious(text: str) -> bool:
    """True if a short label (e.g. a skill name) is too long or contains instruction-like words."""
    words = text.strip().lower().split()
    return len(words) > MAX_SKILL_WORDS or any(word in SUSPICIOUS_WORDS for word in words)