import json
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

# ──────────────────────────────────────────────
# System Prompt — [Role]+[Expertise]+[Guidelines]+[Output Format]+[Constraints]
# ──────────────────────────────────────────────

EOD_SYSTEM_PROMPT = """\
[Role]
You are a professional report writer specializing in End of Day (EOD) reports \
for software development teams.

[Expertise]
Your expertise is transforming raw daily activity notes into polished, \
narrative-style summaries that read naturally and professionally.

[Guidelines]
- Write in narrative paragraph format with chronological flow through the day
- Use a professional but conversational tone
- Mention meetings, tasks, challenges, and outcomes naturally
- Use transitions like "From there," "Later in the day," "After that"
- Start with how the day began and flow naturally through activities

[Output Format]
- A single concise paragraph of approximately {sentence_count} sentences
- Plain text only, no markdown formatting

[Constraints]
- Do NOT use bullet points, numbered lists, or markdown formatting
- Do NOT add a greeting, sign-off, or date header
- Do NOT fabricate details not present in the input
- Do NOT use overly formal or corporate language
- Keep it concise — no filler sentences
- Strictly around {sentence_count} sentences"""

# ──────────────────────────────────────────────
# Review Prompt — Chain-of-Thought with Self-Verification
# ──────────────────────────────────────────────

REVIEW_SYSTEM_PROMPT = """\
[Role]
You are a quality reviewer for End of Day (EOD) reports.

[Expertise]
You evaluate whether generated reports meet specific style and quality standards.

[Guidelines]
Review the draft step by step against each criterion:

Step 1 - NARRATIVE FORMAT: Is it paragraph form? Any bullet points or numbered lists?
Step 2 - CHRONOLOGICAL FLOW: Does it follow morning to afternoon to evening order?
Step 3 - TONE: Professional but conversational? Not too formal, not too casual?
Step 4 - ACCURACY: Does it only mention activities from the input? Any fabricated details?
Step 5 - LENGTH: Is it a single paragraph of approximately {sentence_count} sentences? Reject if it deviates significantly.
Step 6 - TRANSITIONS: Does it use natural transitions between activities?

After evaluating all steps, decide whether to approve.

[Constraints]
- Only reject if a criterion is clearly violated
- Provide specific, actionable feedback when rejecting"""

# ──────────────────────────────────────────────
# Prompt Templates
# ──────────────────────────────────────────────

GENERATE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EOD_SYSTEM_PROMPT),
        (
            "human",
            "Here are example EOD reports for reference on tone and style:\n\n"
            "{few_shot_examples}\n\n"
            "---\n\n"
            "Now transform these activity notes into a narrative EOD report:\n\n"
            "{activities_text}\n\n"
            "Write the EOD report narrative:",
        ),
    ]
)

REVIEW_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", REVIEW_SYSTEM_PROMPT),
        (
            "human",
            "Original activity notes:\n{activities_text}\n\n"
            "Generated EOD report:\n{draft}\n\n"
            "Review this report against the criteria:",
        ),
    ]
)

REVISE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EOD_SYSTEM_PROMPT),
        (
            "human",
            "Here are example EOD reports for reference:\n\n"
            "{few_shot_examples}\n\n"
            "---\n\n"
            "Activity notes:\n{activities_text}\n\n"
            "Previous draft:\n{draft}\n\n"
            "Reviewer feedback:\n{feedback}\n\n"
            "Please revise the EOD report based on the feedback:",
        ),
    ]
)


# ──────────────────────────────────────────────
# Few-Shot Examples (loaded from examples.json)
# ──────────────────────────────────────────────

_EXAMPLES_PATH = Path(__file__).parent / "examples.json"


def load_few_shot_examples() -> list[dict]:
    with open(_EXAMPLES_PATH, encoding="utf-8") as f:
        return json.load(f)


def format_few_shot_examples() -> str:
    """Format few-shot examples into a string for the prompt."""
    examples = load_few_shot_examples()
    parts = []
    for i, ex in enumerate(examples, 1):
        parts.append(f"Example {i}:\nInput:\n{ex['input']}\n\nOutput:\n{ex['output']}")
    return "\n\n---\n\n".join(parts)


def format_activities_for_prompt(grouped: dict) -> str:
    """Convert grouped activities dict into a formatted string for the prompt."""
    lines = []
    for period in ["morning", "afternoon", "evening"]:
        items = grouped.get(period, [])
        if items:
            lines.append(f"{period.capitalize()}:")
            for item in items:
                time_str = item.get("time", "")
                content = item.get("content", "")
                lines.append(
                    f"- [{time_str}] {content}" if time_str else f"- {content}"
                )
    return "\n".join(lines)
