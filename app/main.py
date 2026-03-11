from contextlib import asynccontextmanager
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import init_db, SessionLocal
from app.services.activity_service import activity_service
from app.services.report_service import report_service
from app.agent.graph import eod_agent
from app.api.v1.router import api_router
from app.api.v1.endpoints.pages import router as pages_router

scheduler = BackgroundScheduler()


def scheduled_eod_generation():
    """Called by APScheduler at the configured time."""
    db = SessionLocal()
    try:
        today = date.today()
        activities = activity_service.get_by_date(db, today)
        if not activities:
            print("[Scheduler] No activities logged today. Skipping.")
            return

        print(f"[Scheduler] Generating EOD for {today}...")
        result = eod_agent.invoke(
            {
                "date": today.isoformat(),
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
        report_service.save(db, today, narrative)
        print(
            f"[Scheduler] EOD draft saved. Visit /reports/preview to review and post."
        )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()

    settings = get_settings()
    hour, minute = map(int, settings.EOD_SCHEDULE_TIME.split(":"))
    scheduler.add_job(
        scheduled_eod_generation,
        "cron",
        hour=hour,
        minute=minute,
        id="eod_generation",
    )
    scheduler.start()
    print(f"[Scheduler] EOD generation scheduled daily at {settings.EOD_SCHEDULE_TIME}")

    yield

    # Shutdown
    scheduler.shutdown()


app = FastAPI(title="EOD Reporter", lifespan=lifespan)

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# API routes (JSON endpoints)
app.include_router(api_router)

# Page routes (HTML — mounted at root, not under /api/v1)
app.include_router(pages_router)
