from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, Text, DateTime, Date, Enum
from sqlalchemy.sql import func

from app.core.database import Base


class ReportStatus(str, PyEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    POSTED = "posted"


class EODReport(Base):
    __tablename__ = "eod_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, unique=True, nullable=False)
    narrative = Column(Text, nullable=False)
    status = Column(Enum(ReportStatus), default=ReportStatus.DRAFT, nullable=False)
    generated_at = Column(DateTime, default=func.now(), nullable=False)
    posted_at = Column(DateTime, nullable=True)
