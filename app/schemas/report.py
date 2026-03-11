from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.report import ReportStatus


class EODReportResponse(BaseModel):
    id: int
    date: date
    narrative: str
    status: ReportStatus
    generated_at: datetime
    posted_at: Optional[datetime]

    class Config:
        from_attributes = True


class EODReportUpdate(BaseModel):
    narrative: str


class ReviewResult(BaseModel):
    """Structured output from the LangGraph self-review node."""

    approved: bool = Field(description="Whether the draft meets all quality criteria")
    feedback: str = Field(
        description="Specific feedback if not approved, or 'Looks good' if approved"
    )
