from datetime import date

from sqlalchemy.orm import Session

from app.models.activity import Activity
from app.repositories.base import BaseRepository


class ActivityRepository(BaseRepository[Activity]):
    def __init__(self):
        super().__init__(Activity)

    def get_by_date(self, db: Session, target_date: date) -> list[Activity]:
        return (
            db.query(Activity)
            .filter(Activity.date == target_date)
            .order_by(Activity.logged_at)
            .all()
        )

    def get_grouped_by_period(
        self, db: Session, target_date: date
    ) -> dict[str, list[Activity]]:
        activities = self.get_by_date(db, target_date)
        grouped = {"morning": [], "afternoon": [], "evening": []}
        for a in activities:
            period = a.effective_time_period.value
            grouped[period].append(a)
        return grouped


activity_repo = ActivityRepository()
