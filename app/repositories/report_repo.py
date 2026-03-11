from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.report import EODReport, ReportStatus
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository[EODReport]):
    def __init__(self):
        super().__init__(EODReport)

    def get_by_date(self, db: Session, target_date: date) -> Optional[EODReport]:
        return db.query(EODReport).filter(EODReport.date == target_date).first()

    def save_or_update(
        self, db: Session, target_date: date, narrative: str
    ) -> EODReport:
        report = self.get_by_date(db, target_date)
        if report:
            report.narrative = narrative
            report.status = ReportStatus.DRAFT
            report.generated_at = datetime.now()
        else:
            report = EODReport(
                date=target_date,
                narrative=narrative,
                status=ReportStatus.DRAFT,
            )
            db.add(report)
        db.commit()
        db.refresh(report)
        return report

    def update_narrative(
        self, db: Session, report_id: int, narrative: str
    ) -> Optional[EODReport]:
        report = self.get(db, report_id)
        if not report:
            return None
        report.narrative = narrative
        db.commit()
        db.refresh(report)
        return report

    def mark_posted(self, db: Session, report_id: int) -> Optional[EODReport]:
        report = self.get(db, report_id)
        if not report:
            return None
        report.status = ReportStatus.POSTED
        report.posted_at = datetime.now()
        db.commit()
        db.refresh(report)
        return report

    def get_history(self, db: Session, limit: int = 30) -> list[EODReport]:
        return db.query(EODReport).order_by(EODReport.date.desc()).limit(limit).all()


report_repo = ReportRepository()
