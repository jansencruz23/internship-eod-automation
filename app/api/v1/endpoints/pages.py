from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
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
    auto_post_internity_enabled = (
        settings.auto_post_internity_enabled if settings else False
    )
    schedule_time = settings.schedule_time if settings else "15:35"
    report = report_service.get_by_date(db, today)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "today": today,
            "grouped_activities": grouped,
            "has_activities": len(all_activities) > 0,
            "has_report": report is not None,
            "auto_post_enabled": auto_post_enabled,
            "auto_post_internity_enabled": auto_post_internity_enabled,
            "schedule_time": schedule_time,
        },
    )


@router.get("/reports/preview", response_class=HTMLResponse)
def preview_report(
    request: Request,
    target_date: Optional[date] = None,
    error: Optional[str] = None,
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
            "error": error,
        },
    )


@router.get("/reports/history", response_class=HTMLResponse)
def report_history(request: Request, db: Session = Depends(get_db)):
    reports = report_service.get_history(db)
    return templates.TemplateResponse(
        "history.html",
        {"request": request, "reports": reports},
    )


@router.get("/reports/monthly", response_class=HTMLResponse)
def monthly_summary_page(
    request: Request,
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    # Build list of available months (months that have reports)
    reports = report_service.get_by_month(db, target_year, target_month)

    # Check for cached weekly summaries in session (generated via POST)
    return templates.TemplateResponse(
        "monthly.html",
        {
            "request": request,
            "year": target_year,
            "month": target_month,
            "month_name": date(target_year, target_month, 1).strftime("%B %Y"),
            "reports": reports,
            "weekly_summaries": None,
        },
    )
