from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, Text, DateTime, Date, Enum
from sqlalchemy.sql import func

from app.core.database import Base


class TimePeriod(str, PyEnum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text, nullable=False)
    logged_at = Column(DateTime, default=func.now(), nullable=False)
    date = Column(Date, default=date.today, nullable=False)
    time_period = Column(Enum(TimePeriod), nullable=False)
    time_period_override = Column(Enum(TimePeriod), nullable=True)

    @staticmethod
    def compute_time_period(dt: datetime) -> TimePeriod:
        """Auto-categorize: morning < 12, afternoon 12-17, evening >= 17."""
        hour = dt.hour
        if hour < 12:
            return TimePeriod.MORNING
        elif hour < 17:
            return TimePeriod.AFTERNOON
        else:
            return TimePeriod.EVENING

    @property
    def effective_time_period(self) -> TimePeriod:
        """Return override if set, otherwise auto-computed period."""
        return self.time_period_override or self.time_period
