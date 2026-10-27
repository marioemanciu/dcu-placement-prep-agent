"""Single wrapper for all LLM calls, so the model can be swapped in one place."""
import json
import ollama

MODEL = "llama3.1:8b"


def call_llm(system: str, user: str, json_output: bool = False, temperature: float = 0.3) -> str:
    """Send one request to the local Ollama model and return its text response."""
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        format="json" if json_output else "",
        options={"temperature": temperature},
    )
    return response["message"]["content"]


def call_llm_json(system: str, user: str, retries: int = 1, **kwargs) -> dict:
    """Call the LLM expecting JSON; retry once on invalid output (Phase 2 design)."""
    for attempt in range(retries + 1):
        raw = call_llm(system, user, json_output=True, **kwargs)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            if attempt == retries:
                raise
