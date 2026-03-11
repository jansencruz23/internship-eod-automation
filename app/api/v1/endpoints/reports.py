from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.dependencies import get_teams_poster
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
