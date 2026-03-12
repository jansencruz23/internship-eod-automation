from datetime import date

from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy.orm import Session

from app.agent.state import EODState
from app.agent.teams.prompts import (
    GENERATE_PROMPT,
    REVIEW_PROMPT,
    REVISE_PROMPT,
    format_few_shot_examples,
    format_activities_for_prompt,
)
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.schemas.report import ReviewResult
from app.services.activity_service import activity_service


# ──────────────────────────────────────────────
# LLM Initialization (Gemini)
# ──────────────────────────────────────────────

_llm: ChatGoogleGenerativeAI | None = None


def get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        settings = get_settings()
        _llm = ChatGoogleGenerativeAI(
            model=settings.MODEL_NAME,
            google_api_key=settings.GOOGLE_API_KEY,
            max_output_tokens=1024,
        )
    return _llm


# ──────────────────────────────────────────────
# Node: Fetch activities from database
# ──────────────────────────────────────────────


def fetch_activities(state: EODState) -> dict:
    target_date = date.fromisoformat(state["date"])
    db: Session = SessionLocal()
    try:
        grouped = activity_service.get_grouped(db, target_date)

        activities_list = []
        grouped_dict = {}
        for period, items in grouped.items():
            period_list = []
            for a in items:
                entry = {
                    "content": a.content,
                    "time": a.logged_at.strftime("%H:%M"),
                    "period": a.effective_time_period.value,
                }
                activities_list.append(entry)
                period_list.append(entry)
            grouped_dict[period] = period_list

        return {
            "activities": activities_list,
            "grouped_activities": grouped_dict,
        }
    finally:
        db.close()


# ──────────────────────────────────────────────
# Node: Generate narrative draft
# ──────────────────────────────────────────────


def generate_draft(state: EODState) -> dict:
    llm = get_llm()
    chain = GENERATE_PROMPT | llm

    activities_text = format_activities_for_prompt(state["grouped_activities"])
    few_shot = format_few_shot_examples()

    response = chain.invoke(
        {
            "few_shot_examples": few_shot,
            "activities_text": activities_text,
        }
    )

    return {"draft": response.content.strip()}


# ──────────────────────────────────────────────
# Node: Self-review (structured output)
# ──────────────────────────────────────────────


def self_review(state: EODState) -> dict:
    llm = get_llm()
    activities_text = format_activities_for_prompt(state["grouped_activities"])

    try:
        # Use structured output — eliminates fragile string parsing
        structured_llm = llm.with_structured_output(ReviewResult)
        chain = REVIEW_PROMPT | structured_llm

        result: ReviewResult = chain.invoke(
            {
                "activities_text": activities_text,
                "draft": state["draft"],
            }
        )

        return {
            "review_feedback": result.feedback,
            "review_approved": result.approved,
            "revision_count": state.get("revision_count", 0)
            + (0 if result.approved else 1),
        }
    except Exception:
        # Fallback: accept the draft if structured output fails
        return {
            "review_feedback": "Review unavailable — accepting draft.",
            "review_approved": True,
            "revision_count": state.get("revision_count", 0),
        }


# ──────────────────────────────────────────────
# Node: Revise draft based on feedback
# ──────────────────────────────────────────────


def revise_draft(state: EODState) -> dict:
    llm = get_llm()
    chain = REVISE_PROMPT | llm

    activities_text = format_activities_for_prompt(state["grouped_activities"])
    few_shot = format_few_shot_examples()

    response = chain.invoke(
        {
            "few_shot_examples": few_shot,
            "activities_text": activities_text,
            "draft": state["draft"],
            "feedback": state["review_feedback"],
        }
    )

    return {"draft": response.content.strip()}
