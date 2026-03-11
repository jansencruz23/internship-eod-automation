from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.activity import ActivityCreate, ActivityResponse, ActivityUpdate
from app.services.activity_service import activity_service

router = APIRouter()


@router.post("/", response_model=ActivityResponse)
def create_activity(payload: ActivityCreate, db: Session = Depends(get_db)):
    activity = activity_service.log_activity(
        db,
        content=payload.content,
        time_period_override=payload.time_period_override,
    )
    return ActivityResponse(
        id=activity.id,
        content=activity.content,
        logged_at=activity.logged_at,
        date=activity.date,
        time_period=activity.time_period,
        time_period_override=activity.time_period_override,
        effective_time_period=activity.effective_time_period,
    )


@router.get("/", response_model=list[ActivityResponse])
def list_activities(target_date: Optional[date] = None, db: Session = Depends(get_db)):
    target = target_date or date.today()
    activities = activity_service.get_by_date(db, target)
    return [
        ActivityResponse(
            id=a.id,
            content=a.content,
            logged_at=a.logged_at,
            date=a.date,
            time_period=a.time_period,
            time_period_override=a.time_period_override,
            effective_time_period=a.effective_time_period,
        )
        for a in activities
    ]


@router.put("/{activity_id}", response_model=ActivityResponse)
def update_activity(
    activity_id: int,
    payload: ActivityUpdate,
    db: Session = Depends(get_db),
):
    updates = payload.model_dump(exclude_none=True)
    activity = activity_service.update(db, activity_id, **updates)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return ActivityResponse(
        id=activity.id,
        content=activity.content,
        logged_at=activity.logged_at,
        date=activity.date,
        time_period=activity.time_period,
        time_period_override=activity.time_period_override,
        effective_time_period=activity.effective_time_period,
    )


@router.delete("/{activity_id}")
def delete_activity(activity_id: int, db: Session = Depends(get_db)):
    if not activity_service.delete(db, activity_id):
        raise HTTPException(status_code=404, detail="Activity not found")
    return {"ok": True}


@router.post("/log")
def log_from_form(content: str = Form(...), db: Session = Depends(get_db)):
    """HTMX form endpoint — logs activity and redirects to dashboard."""
    activity_service.log_activity(db, content=content)
    return RedirectResponse(url="/", status_code=303)
