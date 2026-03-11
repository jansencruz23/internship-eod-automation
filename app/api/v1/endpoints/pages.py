from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.settings import AppSettings
from app.services.activity_service import activity_service
from app.services.report_service import report_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    grouped = activity_service.get_grouped(db, today)
    all_activities = activity_service.get_by_date(db, today)
    settings = db.query(AppSettings).first()
    auto_post_enabled = settings.auto_post_enabled if settings else False
    schedule_time = settings.schedule_time if settings else "15:35"
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "today": today,
            "grouped_activities": grouped,
            "has_activities": len(all_activities) > 0,
            "auto_post_enabled": auto_post_enabled,
            "schedule_time": schedule_time,
        },
    )


@router.get("/reports/preview", response_class=HTMLResponse)
def preview_report(
    request: Request,
    target_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    target = target_date or date.today()
    report = report_service.get_by_date(db, target)
    return templates.TemplateResponse(
        "preview.html",
        {
            "request": request,
            "report": report,
            "target_date": target,
        },
    )


@router.get("/reports/history", response_class=HTMLResponse)
def report_history(request: Request, db: Session = Depends(get_db)):
    reports = report_service.get_history(db)
    return templates.TemplateResponse(
        "history.html",
        {"request": request, "reports": reports},
    )
