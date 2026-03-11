from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.activity import Activity, TimePeriod
from app.repositories.activity_repo import activity_repo


class ActivityService:
    def __init__(self):
        self.repo = activity_repo

    def log_activity(
        self,
        db: Session,
        content: str,
        time_period_override: Optional[TimePeriod] = None,
    ) -> Activity:
        now = datetime.now()
        activity = Activity(
            content=content,
            logged_at=now,
            date=now.date(),
            time_period=Activity.compute_time_period(now),
            time_period_override=time_period_override,
        )
        db.add(activity)
        db.commit()
        db.refresh(activity)
        return activity

    def get_by_date(self, db: Session, target_date: date) -> list[Activity]:
        return self.repo.get_by_date(db, target_date)

    def get_grouped(self, db: Session, target_date: date) -> dict[str, list[Activity]]:
        return self.repo.get_grouped_by_period(db, target_date)

    def update(self, db: Session, activity_id: int, **kwargs) -> Optional[Activity]:
        activity = self.repo.get(db, activity_id)
        if not activity:
            return None
        for key, value in kwargs.items():
            if value is not None:
                setattr(activity, key, value)
        db.commit()
        db.refresh(activity)
        return activity

    def delete(self, db: Session, activity_id: int) -> bool:
        return self.repo.delete(db, activity_id)


activity_service = ActivityService()
