from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.activity import TimePeriod


class ActivityCreate(BaseModel):
    content: str = Field(..., min_length=1, description="What you did")
    time_period_override: Optional[TimePeriod] = Field(
        None, description="Override auto time period (morning/afternoon/evening)"
    )


class ActivityResponse(BaseModel):
    id: int
    content: str
    logged_at: datetime
    date: date
    time_period: TimePeriod
    time_period_override: Optional[TimePeriod]
    effective_time_period: TimePeriod

    class Config:
        from_attributes = True


class ActivityUpdate(BaseModel):
    content: Optional[str] = None
    time_period_override: Optional[TimePeriod] = None
