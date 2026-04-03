from app.agent.llm import get_llm
from app.agent.teams.prompts import format_activities_for_prompt
from app.agent.internity.prompts import INTERNITY_EXTRACT_PROMPT, INTERNITY_FEW_SHOT
from app.schemas.report import InternityEOD


def generate_internity_eod(
    grouped_activities: dict, max_retries: int = 2
) -> InternityEOD:
    """Generate structured Internity EOD data from grouped activities.

    Uses the shared get_llm() singleton and .with_structured_output() pattern.
    Retries on parsing failures since LLM structured output can be flaky.
    """
    llm = get_llm()
    structured_llm = llm.with_structured_output(InternityEOD)
    chain = INTERNITY_EXTRACT_PROMPT | structured_llm

    activities_text = format_activities_for_prompt(grouped_activities)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result: InternityEOD = chain.invoke(
                {
                    "few_shot": INTERNITY_FEW_SHOT,
                    "activities_text": activities_text,
                }
            )
            return result
        except Exception as e:
            last_error = e
            print(
                f"[Internity] Structured output attempt {attempt + 1} failed: {e}"
            )

    raise last_error
