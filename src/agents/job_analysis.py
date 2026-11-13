# Job-Analysis agent - extracts requirements, role level, and interview topics.
#
# Created by    : Maksym Sharai
# Date          : 11/11/2026


import sys
from pathlib import Path

# Make sure the project root is on the import path so local modules can be
# imported cleanly when this file runs from different directories.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import helper functions and the output schema used by this agent.
# These come from the project codebase, not from Python's built-in modules.
from src.llm import format_data_context, generate_structured
from src.schemas import JobAnalysisOutput


# Load the system prompt text from the prompt file.
# This helps guide the LLM with instructions about what to extract.
SYSTEM_PROMPT = (PROJECT_ROOT / "prompts" / "job_analysis.md").read_text(
    encoding="utf-8"
)


def analyze_job(job_description: str) -> JobAnalysisOutput:
    """Extract job requirements, experience level, and likely interview topics."""

    # Validate the input before sending it to the LLM.
    # A blank or non-string value would cause confusing results.
    if not isinstance(job_description, str) or not job_description.strip():
        raise ValueError("job_description must be a non-empty string")

    # Clean the job description and wrap it in a standard data format.
    # This makes it easier for the model to process the input consistently.
    job_context = format_data_context(job_description.strip(), "job_description")

    # Build a prompt that tells the model what to do.
    # We ask it to find technical skills, behavioural skills, experience level,
    # and likely interview topics, while grounding all results in the description.
    prompt = (
        "Analyze the job description below. Extract all required technical and "
        "behavioural skills, identify the role's experience level, and predict "
        "the likely interview topics. Ground the results in the job description.\n\n"
        f"{job_context}"
    )

    # Send the prompt and system instructions to the LLM and parse the response
    # into the JobAnalysisOutput structure defined in the project schema.
    return generate_structured(prompt, SYSTEM_PROMPT, JobAnalysisOutput)


# Alias for easier use elsewhere in the project.
# This lets other modules call job_analysis_agent(...) the same way as analyze_job(...).
job_analysis_agent = analyze_job


if __name__ == "__main__":
    sample_aws_job_description = """
    AWS Software Development Engineer Intern - DynamoDB Team, Dublin

    Amazon Web Services is seeking a software engineering intern to join the
    DynamoDB team. You will work on highly reliable, large-scale distributed
    systems and help design, implement, and test features that improve
    performance, availability, and developer experience. The role involves
    coding in Java, Python, or C++, building and debugging backend services,
    writing automated tests, and collaborating with engineers across teams.
    You will participate in technical design reviews, contribute to system
    architecture discussions, and analyze production issues using logs,
    metrics, and tracing tools. Candidates should be pursuing a degree in
    computer science, engineering, or a related field, with strong problem-
    solving skills, curiosity, and excellent communication. Experience with
    distributed systems, databases, cloud computing, or AWS services is a plus.
    """

    aws_analysis = analyze_job(sample_aws_job_description)
    print("\nRequired skills:", aws_analysis.required_skills)
    print("Experience level:", aws_analysis.experience_level)
    print("Likely topics:", aws_analysis.likely_topics)
