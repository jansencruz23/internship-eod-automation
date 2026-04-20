from contextlib import asynccontextmanager
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import init_db, SessionLocal
from app.models.settings import AppSettings
from app.services.activity_service import activity_service
from app.services.report_service import report_service
from app.services.teams.poster import TeamsPoster
from app.agent.teams.graph import eod_agent
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

        app_settings_row = db.query(AppSettings).first()
        sentence_count = (
            app_settings_row.teams_sentence_count
            if app_settings_row and app_settings_row.teams_sentence_count
            else 5
        )

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
                "sentence_count": sentence_count,
            }
        )
        narrative = result.get("final_narrative", result.get("draft", ""))
        report = report_service.save(db, today, narrative)

        # Check Teams auto-post setting
        if app_settings_row and app_settings_row.auto_post_enabled:
            try:
                settings = get_settings()
                poster = TeamsPoster(settings.POWER_AUTOMATE_URL)
                poster.post(report)
                report_service.mark_posted(db, report.id)
                print("[Scheduler] Auto-posted to Teams.")
            except Exception as e:
                print(f"[Scheduler] Teams auto-post failed: {e}")
        else:
            print("[Scheduler] Draft saved. Visit /reports/preview to review and post.")

        # Check Internity auto-post setting
        if app_settings_row and app_settings_row.auto_post_internity_enabled:
            try:
                settings = get_settings()
                if settings.INTERNITY_USERNAME and settings.INTERNITY_FORM_URL:
                    from app.services.internity.poster import InternityPoster
                    from app.agent.internity.nodes import generate_internity_eod

                    grouped = activity_service.get_grouped(db, today)
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

                    internity_eod = generate_internity_eod(grouped_dict)
                    poster = InternityPoster(
                        username=settings.INTERNITY_USERNAME,
                        password=settings.INTERNITY_PASSWORD,
                        form_url=settings.INTERNITY_FORM_URL,
                    )
                    poster.post(internity_eod, today, auto_submit=False)
                    print("[Scheduler] Internity form opened — review and submit manually.")
                else:
                    print("[Scheduler] Internity credentials not configured. Skipping.")
            except Exception as e:
                print(f"[Scheduler] Internity auto-post failed: {e}")

    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()

    db = SessionLocal()
    try:
        app_settings_row = db.query(AppSettings).first()
        if app_settings_row and app_settings_row.schedule_time:
            schedule_time = app_settings_row.schedule_time
        else:
            schedule_time = get_settings().EOD_SCHEDULE_TIME
    finally:
        db.close()

    hour, minute = map(int, schedule_time.split(":"))
    scheduler.add_job(
        scheduled_eod_generation,
        "cron",
        hour=hour,
        minute=minute,
        id="eod_generation",
        misfire_grace_time=60,
    )
    scheduler.start()
    print(f"[Scheduler] EOD generation scheduled daily at {schedule_time}")

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
