import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_teams_poster
from app.models.settings import AppSettings
from app.services.activity_service import activity_service
from app.services.report_service import report_service
from app.services.teams_service import TeamsPoster
from app.agent.graph import eod_agent

router = APIRouter()


@router.post("/generate")
def generate_report(target_date: Optional[date] = None, db: Session = Depends(get_db)):
    target = target_date or date.today()

    activities = activity_service.get_by_date(db, target)
    if not activities:
        raise HTTPException(
            status_code=400, detail="No activities logged for this date"
        )

    result = eod_agent.invoke(
        {
            "date": target.isoformat(),
            "activities": [],
            "grouped_activities": {},
            "draft": "",
            "review_feedback": "",
            "review_approved": False,
            "revision_count": 0,
            "final_narrative": "",
        }
    )

    narrative = result.get("final_narrative", result.get("draft", ""))
    report = report_service.save(db, target, narrative)

    return RedirectResponse(
        url=f"/reports/preview?target_date={target}", status_code=303
    )


@router.post("/{report_id}/update")
def update_narrative(
    report_id: int,
    narrative: str = Form(...),
    db: Session = Depends(get_db),
):
    report = report_service.update_narrative(db, report_id, narrative)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return RedirectResponse(
        url=f"/reports/preview?target_date={report.date}", status_code=303
    )


@router.post("/{report_id}/post-to-teams")
def post_to_teams(
    report_id: int,
    db: Session = Depends(get_db),
    poster: TeamsPoster = Depends(get_teams_poster),
):
    report = report_service.repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        poster.post(report)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to post to Teams: {e}")

    report_service.mark_posted(db, report_id)
    return RedirectResponse(
        url=f"/reports/preview?target_date={report.date}", status_code=303
    )


def _render_toggle(enabled: bool) -> str:
    checked = "checked" if enabled else ""
    label = "ON" if enabled else "OFF"
    return f"""
    <label class="toggle-switch">
        <input type="checkbox" {checked}
               hx-post="/reports/toggle-auto-post"
               hx-target="#toggle-container"
               hx-swap="innerHTML">
        <span class="slider"></span>
    </label>
    <span class="toggle-label toggle-{'on' if enabled else 'off'}">{label}</span>
    """


@router.post("/toggle-auto-post")
def toggle_auto_post(db: Session = Depends(get_db)):
    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings(auto_post_enabled=True)
        db.add(settings)
    else:
        settings.auto_post_enabled = not settings.auto_post_enabled
    db.commit()
    db.refresh(settings)
    return HTMLResponse(_render_toggle(settings.auto_post_enabled))


def _render_time(time_str: str, saved: bool = False) -> str:
    msg = '<span class="save-confirm">Saved!</span>' if saved else ""
    return f"""
    <input type="time" name="schedule_time" value="{time_str}"
           hx-post="/reports/update-schedule-time"
           hx-target="#time-container"
           hx-swap="innerHTML"
           hx-trigger="change">
    {msg}
    """


@router.post("/update-schedule-time")
def update_schedule_time(
    schedule_time: str = Form(...),
    db: Session = Depends(get_db),
):
    if not re.match(r"^\d{2}:\d{2}$", schedule_time):
        raise HTTPException(status_code=400, detail="Invalid time format")

    hour, minute = map(int, schedule_time.split(":"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise HTTPException(status_code=400, detail="Invalid time value")

    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings(schedule_time=schedule_time)
        db.add(settings)
    else:
        settings.schedule_time = schedule_time
    db.commit()

    # Reschedule the APScheduler job
    from app.main import scheduler
    scheduler.reschedule_job(
        "eod_generation",
        trigger="cron",
        hour=hour,
        minute=minute,
    )
    print(f"[Scheduler] Rescheduled to {schedule_time}")

    return HTMLResponse(_render_time(schedule_time, saved=True))
