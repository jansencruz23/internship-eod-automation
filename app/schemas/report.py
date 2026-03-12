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


class InternityTask(BaseModel):
    """A single task entry for the Internity EOD form."""

    description: str = Field(
        description="Task title and description, e.g. 'Team Huddle & Multi-Attachment Fix — Huddled with the team...'"
    )
    hours: int = Field(
        description="Estimated hours spent on this task (0-8)", ge=0, le=8
    )
    minutes: int = Field(
        description="Estimated remaining minutes spent on this task (0-59)",
        ge=0,
        le=59,
    )


class InternityEOD(BaseModel):
    """Structured output matching the aufccs.org EOD form fields."""

    tasks: list[InternityTask] = Field(
        description="List of tasks performed today, each with description and time estimate"
    )
    key_successes: str = Field(
        description="Key successes and accomplishments for the day"
    )
    main_challenges: str = Field(
        description="Main challenges or difficulties encountered"
    )
    plans_for_tomorrow: str = Field(
        description="Planned tasks and goals for the next working day"
    )
