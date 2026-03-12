import json
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

# ... (all prompt strings stay the same) ...

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
