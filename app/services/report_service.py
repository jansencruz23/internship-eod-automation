from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.report import EODReport
from app.repositories.report_repo import report_repo


class ReportService:
    def __init__(self):
        self.repo = report_repo

    def get_by_date(self, db: Session, target_date: date) -> Optional[EODReport]:
        return self.repo.get_by_date(db, target_date)

    def save(self, db: Session, target_date: date, narrative: str) -> EODReport:
        return self.repo.save_or_update(db, target_date, narrative)

    def update_narrative(
        self, db: Session, report_id: int, narrative: str
    ) -> Optional[EODReport]:
        return self.repo.update_narrative(db, report_id, narrative)

    def mark_posted(self, db: Session, report_id: int) -> Optional[EODReport]:
        return self.repo.mark_posted(db, report_id)

    def get_history(self, db: Session, limit: int = 30) -> list[EODReport]:
        return self.repo.get_history(db, limit)

    def get_by_month(
        self, db: Session, year: int, month: int
    ) -> list[EODReport]:
        return self.repo.get_by_month(db, year, month)


report_service = ReportService()
