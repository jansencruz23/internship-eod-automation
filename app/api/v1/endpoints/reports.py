import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_teams_poster, get_internity_poster
from app.models.settings import AppSettings
from app.services.activity_service import activity_service
from app.services.report_service import report_service
from app.services.teams.poster import TeamsPoster
from app.services.internity.poster import InternityPoster
from app.agent.teams.graph import eod_agent
from app.agent.internity.nodes import generate_internity_eod

router = APIRouter()


@router.post("/generate")
def generate_report(target_date: Optional[date] = None, db: Session = Depends(get_db)):
    target = target_date or date.today()

    activities = activity_service.get_by_date(db, target)
    if not activities:
        raise HTTPException(
            status_code=400, detail="No activities logged for this date"
        )

    settings = db.query(AppSettings).first()
    sentence_count = settings.teams_sentence_count if settings and settings.teams_sentence_count else 5

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
            "sentence_count": sentence_count,
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
    <span class="toggle-label toggle-{"on" if enabled else "off"}">{label}</span>
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

    from app.main import scheduler

    scheduler.reschedule_job(
        "eod_generation",
        trigger="cron",
        hour=hour,
        minute=minute,
    )
    print(f"[Scheduler] Rescheduled to {schedule_time}")

    return HTMLResponse(_render_time(schedule_time, saved=True))


def _render_sentence_count(count: int, saved: bool = False) -> str:
    msg = '<span class="save-confirm">Saved!</span>' if saved else ""
    return f"""
    <input type="number" name="sentence_count" value="{count}" min="2" max="10"
           hx-post="/reports/update-sentence-count"
           hx-target="#sentence-count-container"
           hx-swap="innerHTML"
           hx-trigger="change">
    {msg}
    """


@router.post("/update-sentence-count")
def update_sentence_count(
    sentence_count: int = Form(...),
    db: Session = Depends(get_db),
):
    if not (2 <= sentence_count <= 10):
        raise HTTPException(status_code=400, detail="Sentence count must be between 2 and 10")

    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings(teams_sentence_count=sentence_count)
        db.add(settings)
    else:
        settings.teams_sentence_count = sentence_count
    db.commit()

    return HTMLResponse(_render_sentence_count(sentence_count, saved=True))


# ── Internity Integration ──


@router.post("/{report_id}/post-to-internity")
def post_to_internity(
    report_id: int,
    db: Session = Depends(get_db),
    poster: InternityPoster = Depends(get_internity_poster),
):
    from urllib.parse import quote

    report = report_service.repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    grouped = activity_service.get_grouped(db, report.date)
    total = sum(len(v) for v in grouped.values())
    if total == 0:
        raise HTTPException(status_code=400, detail="No activities for this date")

    grouped_dict = {}
    for period, items in grouped.items():
        grouped_dict[period] = [
            {
                "content": a.content,
                "time": a.logged_at.strftime("%H:%M"),
                "period": a.effective_time_period.value,
            }
            for a in items
        ]

    try:
        internity_eod = generate_internity_eod(grouped_dict)
    except Exception as e:
        print(f"[Internity] Failed to generate structured EOD: {e}")
        error_msg = quote(f"Failed to generate Internity data: {e}")
        return RedirectResponse(
            url=f"/reports/preview?target_date={report.date}&error={error_msg}",
            status_code=303,
        )

    # Validate task data before posting
    for task in internity_eod.tasks:
        task.hours = max(0, min(8, task.hours))
        task.minutes = max(0, min(59, task.minutes))

    try:
        poster.post(internity_eod, report.date)
    except Exception as e:
        print(f"[Internity] Failed to submit form: {e}")
        error_msg = quote(f"Failed to submit to Internity: {e}")
        return RedirectResponse(
            url=f"/reports/preview?target_date={report.date}&error={error_msg}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/reports/preview?target_date={report.date}", status_code=303
    )


def _render_internity_toggle(enabled: bool) -> str:
    checked = "checked" if enabled else ""
    label = "ON" if enabled else "OFF"
    state = "on" if enabled else "off"
    return f"""
    <label class="toggle-switch">
        <input type="checkbox" {checked}
               hx-post="/reports/toggle-auto-post-internity"
               hx-target="#internity-toggle-container"
               hx-swap="innerHTML">
        <span class="slider"></span>
    </label>
    <span class="toggle-label toggle-{state}">{label}</span>
    """


@router.post("/toggle-auto-post-internity")
def toggle_auto_post_internity(db: Session = Depends(get_db)):
    settings = db.query(AppSettings).first()
    if not settings:
        settings = AppSettings(auto_post_internity_enabled=True)
        db.add(settings)
    else:
        settings.auto_post_internity_enabled = not settings.auto_post_internity_enabled
    db.commit()
    db.refresh(settings)
    return HTMLResponse(_render_internity_toggle(settings.auto_post_internity_enabled))


# -- Monthly Summary --


@router.post("/generate-monthly-summary")
def generate_monthly_summary_endpoint(
    request: Request,
    year: int = Form(...),
    month: int = Form(...),
    db: Session = Depends(get_db),
):
    from fastapi.templating import Jinja2Templates

    from app.agent.monthly.nodes import generate_monthly_summary

    reports = report_service.get_by_month(db, year, month)
    if not reports:
        raise HTTPException(
            status_code=400, detail="No reports found for this month"
        )

    weekly_summaries = generate_monthly_summary(reports, year, month)

    templates = Jinja2Templates(directory="app/templates")
    month_name = date(year, month, 1).strftime("%B %Y")

    return templates.TemplateResponse(
        "monthly.html",
        {
            "request": request,
            "year": year,
            "month": month,
            "month_name": month_name,
            "reports": reports,
            "weekly_summaries": weekly_summaries,
        },
    )
