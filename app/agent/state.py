from typing import TypedDict


class EODState(TypedDict):
    date: str  # "2026-03-11"
    activities: list[dict]  # [{"content": "...", "time": "09:30", "period": "morning"}]
    grouped_activities: dict  # {"morning": [...], "afternoon": [...], "evening": [...]}
    draft: str  # Current narrative draft
    review_feedback: str  # Feedback from self-review
    review_approved: bool  # Whether the review passed
    revision_count: int  # Number of revisions (cap at 2)
    final_narrative: str  # Approved narrative
    sentence_count: int  # Preferred number of sentences for Teams summary
