# EOD Report Automation — Full Implementation Guide

Automate your daily End of Day reports: log activities throughout the day, let a LangGraph agent compile them into a narrative, preview/edit, and post to Microsoft Teams with one click.

---

## Architecture

```
Throughout the day:
  [CLI: eod log "activity"]  ──►  [SQLite DB]  ◄──  [FastAPI Web UI]
                                  (timestamped, auto-categorized)

End of day (scheduled at 5:00 PM, or manual trigger):
  [APScheduler] ──► [LangGraph Agent] ──► [Preview via Web UI] ──► [User Confirms] ──► [Teams Webhook]
                         │
                    State Graph:
                    1. fetch_activities    → pull today's entries from SQLite
                    2. generate_draft     → Gemini writes narrative EOD
                    3. self_review        → Gemini checks quality (structured output)
                    4. (revise if needed) → loop back, max 2 revisions
                    5. finalize           → return draft for user preview
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Package Manager | **uv** |
| LLM | **Gemini 2.5 Flash** via `langchain-google-genai` |
| LLM Orchestration | **LangGraph** + **LangChain** |
| Web Interface | **FastAPI** + **Jinja2** + **HTMX** |
| CLI | **Typer** + **Rich** |
| Database | **SQLite** via **SQLAlchemy** (sync) |
| Scheduler | **APScheduler** |
| Teams Posting | **Adaptive Card** via Teams Workflows Webhook |
| HTTP Client | **httpx** |

### Skills Applied

- **`fastapi-templates`** — Project structure: `core/`, `models/`, `schemas/`, `repositories/`, `services/`, `api/v1/endpoints/`
- **`architecture-patterns`** — Clean Architecture: repositories as data-access adapters, services as use-case layer
- **`prompt-engineering-patterns`** — System prompt `[Role]+[Expertise]+[Guidelines]+[Format]+[Constraints]`, structured output with Pydantic, CoT self-review, few-shot examples

---

## Project Structure

```
internity/
├── .agents/skills/                         # (existing — unchanged)
├── app/
│   ├── __init__.py
│   ├── main.py                             # FastAPI app + lifespan (APScheduler)
│   ├── cli.py                              # Typer CLI
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                       # Centralized Settings (pydantic-settings)
│   │   └── database.py                     # Engine, SessionLocal, Base, get_db
│   ├── models/
│   │   ├── __init__.py
│   │   ├── activity.py                     # Activity table + TimePeriod enum
│   │   └── report.py                       # EODReport table + ReportStatus enum
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── activity.py                     # ActivityCreate, ActivityResponse, ActivityUpdate
│   │   └── report.py                       # EODReportResponse, EODReportUpdate, ReviewResult
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py                         # BaseRepository generic CRUD
│   │   ├── activity_repo.py                # Activity-specific queries
│   │   └── report_repo.py                  # Report-specific queries
│   ├── services/
│   │   ├── __init__.py
│   │   ├── activity_service.py             # Activity business logic
│   │   ├── report_service.py               # Report orchestration
│   │   └── teams_service.py                # Teams webhook poster
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py                 # Shared DI (get_settings, get_teams_poster)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py                   # Aggregate v1 router
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── activities.py           # Activity CRUD + HTMX form
│   │           ├── reports.py              # Report generate/preview/post
│   │           └── pages.py                # HTML page routes
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── graph.py                        # LangGraph state graph
│   │   ├── nodes.py                        # Node functions (Gemini LLM)
│   │   ├── state.py                        # EODState TypedDict
│   │   ├── prompts.py                      # Prompt templates
│   │   └── examples.json                   # Few-shot examples
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── preview.html
│   │   └── history.html
│   └── static/
│       └── style.css
├── docs/
│   └── IMPLEMENTATION_GUIDE.md             # This file
├── .env
├── .env.example
├── .gitignore
└── pyproject.toml
```

---

## Step 0: Prerequisites

### Install uv

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip
pip install uv
```

### Get a Google AI API Key

1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Sign in with your Google account
3. Click **"Get API Key"** → **"Create API key"**
4. Copy the key — free, no credit card needed

### Set up Teams Webhook (one-time)

1. Open Microsoft Teams → go to your target channel
2. Click the **`...`** menu on the channel → select **"Workflows"**
3. Search for **"Post to a channel when a webhook request is received"**
4. Name it `EOD Report Webhook`, select your team and channel
5. Click **Create** → copy the generated webhook URL

---

## Step 1: Project Setup

### Initialize with uv

```bash
cd "c:\Users\Jansen Cruz\Desktop\Jansen\internity"

# Initialize uv project
uv init --no-readme

# Add all dependencies
uv add langchain-google-genai langchain-core langgraph
uv add fastapi uvicorn jinja2 python-multipart
uv add typer rich
uv add sqlalchemy httpx
uv add python-dotenv pydantic pydantic-settings
uv add apscheduler
```

### Create folder structure

```bash
mkdir -p app/core
mkdir -p app/models
mkdir -p app/schemas
mkdir -p app/repositories
mkdir -p app/services
mkdir -p app/api/v1/endpoints
mkdir -p app/agent
mkdir -p app/templates
mkdir -p app/static

# Create __init__.py files
touch app/__init__.py
touch app/core/__init__.py
touch app/models/__init__.py
touch app/schemas/__init__.py
touch app/repositories/__init__.py
touch app/services/__init__.py
touch app/api/__init__.py
touch app/api/v1/__init__.py
touch app/api/v1/endpoints/__init__.py
touch app/agent/__init__.py
```

### Create `.env.example`

```ini
# .env.example — Copy to .env and fill in your values

GOOGLE_API_KEY=your-api-key-from-aistudio.google.com
TEAMS_WEBHOOK_URL=https://xxxxx.webhook.office.com/webhookb2/xxxxx
EOD_SCHEDULE_TIME=17:00
MODEL_NAME=gemini-2.5-flash
```

### Create `.env`

```ini
# .env — Your actual values

GOOGLE_API_KEY=your-actual-api-key
TEAMS_WEBHOOK_URL=your-actual-webhook-url
EOD_SCHEDULE_TIME=17:00
MODEL_NAME=gemini-2.5-flash
```

### Create `.gitignore`

```gitignore
.env
__pycache__/
*.pyc
*.db
.venv/
```

### Update `pyproject.toml`

Add this section to your `pyproject.toml` (uv init creates the file, you just add the scripts section):

```toml
[project.scripts]
eod = "app.cli:app"
```

---

## Step 2: Core Layer

### `app/core/config.py`

```python
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    TEAMS_WEBHOOK_URL: str
    EOD_SCHEDULE_TIME: str = "17:00"
    MODEL_NAME: str = "gemini-2.5-flash"
    DATABASE_URL: str = "sqlite:///eod_reporter.db"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

### `app/core/database.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import get_settings


engine = create_engine(
    get_settings().DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)
```

---

## Step 3: Models + Schemas

### `app/models/activity.py`

```python
from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, Text, DateTime, Date, Enum
from sqlalchemy.sql import func

from app.core.database import Base


class TimePeriod(str, PyEnum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text, nullable=False)
    logged_at = Column(DateTime, default=func.now(), nullable=False)
    date = Column(Date, default=date.today, nullable=False)
    time_period = Column(Enum(TimePeriod), nullable=False)
    time_period_override = Column(Enum(TimePeriod), nullable=True)

    @staticmethod
    def compute_time_period(dt: datetime) -> TimePeriod:
        """Auto-categorize: morning < 12, afternoon 12-17, evening >= 17."""
        hour = dt.hour
        if hour < 12:
            return TimePeriod.MORNING
        elif hour < 17:
            return TimePeriod.AFTERNOON
        else:
            return TimePeriod.EVENING

    @property
    def effective_time_period(self) -> TimePeriod:
        """Return override if set, otherwise auto-computed period."""
        return self.time_period_override or self.time_period
```

### `app/models/report.py`

```python
from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, Text, DateTime, Date, Enum
from sqlalchemy.sql import func

from app.core.database import Base


class ReportStatus(str, PyEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    POSTED = "posted"


class EODReport(Base):
    __tablename__ = "eod_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, unique=True, nullable=False)
    narrative = Column(Text, nullable=False)
    status = Column(Enum(ReportStatus), default=ReportStatus.DRAFT, nullable=False)
    generated_at = Column(DateTime, default=func.now(), nullable=False)
    posted_at = Column(DateTime, nullable=True)
```

### `app/schemas/activity.py`

```python
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.activity import TimePeriod


class ActivityCreate(BaseModel):
    content: str = Field(..., min_length=1, description="What you did")
    time_period_override: Optional[TimePeriod] = Field(
        None, description="Override auto time period (morning/afternoon/evening)"
    )


class ActivityResponse(BaseModel):
    id: int
    content: str
    logged_at: datetime
    date: date
    time_period: TimePeriod
    time_period_override: Optional[TimePeriod]
    effective_time_period: TimePeriod

    class Config:
        from_attributes = True


class ActivityUpdate(BaseModel):
    content: Optional[str] = None
    time_period_override: Optional[TimePeriod] = None
```

### `app/schemas/report.py`

```python
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.report import ReportStatus


class EODReportResponse(BaseModel):
    id: int
    date: date
    narrative: str
    status: ReportStatus
    generated_at: datetime
    posted_at: Optional[datetime]

    class Config:
        from_attributes = True


class EODReportUpdate(BaseModel):
    narrative: str


class ReviewResult(BaseModel):
    """Structured output from the LangGraph self-review node."""
    approved: bool = Field(description="Whether the draft meets all quality criteria")
    feedback: str = Field(description="Specific feedback if not approved, or 'Looks good' if approved")
```

---

## Step 4: Repositories

### `app/repositories/base.py`

```python
from typing import Generic, TypeVar, Type, Optional

from sqlalchemy.orm import Session

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, db: Session, id: int) -> Optional[ModelType]:
        return db.query(self.model).filter(self.model.id == id).first()

    def get_multi(self, db: Session, skip: int = 0, limit: int = 100) -> list[ModelType]:
        return db.query(self.model).offset(skip).limit(limit).all()

    def delete(self, db: Session, id: int) -> bool:
        obj = self.get(db, id)
        if obj:
            db.delete(obj)
            db.commit()
            return True
        return False
```

### `app/repositories/activity_repo.py`

```python
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

    def get_grouped_by_period(self, db: Session, target_date: date) -> dict[str, list[Activity]]:
        activities = self.get_by_date(db, target_date)
        grouped = {"morning": [], "afternoon": [], "evening": []}
        for a in activities:
            period = a.effective_time_period.value
            grouped[period].append(a)
        return grouped


activity_repo = ActivityRepository()
```

### `app/repositories/report_repo.py`

```python
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.report import EODReport, ReportStatus
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository[EODReport]):
    def __init__(self):
        super().__init__(EODReport)

    def get_by_date(self, db: Session, target_date: date) -> Optional[EODReport]:
        return db.query(EODReport).filter(EODReport.date == target_date).first()

    def save_or_update(self, db: Session, target_date: date, narrative: str) -> EODReport:
        report = self.get_by_date(db, target_date)
        if report:
            report.narrative = narrative
            report.status = ReportStatus.DRAFT
            report.generated_at = datetime.now()
        else:
            report = EODReport(
                date=target_date,
                narrative=narrative,
                status=ReportStatus.DRAFT,
            )
            db.add(report)
        db.commit()
        db.refresh(report)
        return report

    def update_narrative(self, db: Session, report_id: int, narrative: str) -> Optional[EODReport]:
        report = self.get(db, report_id)
        if not report:
            return None
        report.narrative = narrative
        db.commit()
        db.refresh(report)
        return report

    def mark_posted(self, db: Session, report_id: int) -> Optional[EODReport]:
        report = self.get(db, report_id)
        if not report:
            return None
        report.status = ReportStatus.POSTED
        report.posted_at = datetime.now()
        db.commit()
        db.refresh(report)
        return report

    def get_history(self, db: Session, limit: int = 30) -> list[EODReport]:
        return (
            db.query(EODReport)
            .order_by(EODReport.date.desc())
            .limit(limit)
            .all()
        )


report_repo = ReportRepository()
```

---

## Step 5: Services

### `app/services/activity_service.py`

```python
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
```

### `app/services/report_service.py`

```python
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.report import EODReport
from app.repositories.report_repo import report_repo


class ReportService:
    def __init__(self):
        self.repo = report_repo

    def get_by_date(self, db: Session, target_date: date) -> Optional[EODReport]:
        return self.repo.get_by_date(db, target_date)

    def save(self, db: Session, target_date: date, narrative: str) -> EODReport:
        return self.repo.save_or_update(db, target_date, narrative)

    def update_narrative(self, db: Session, report_id: int, narrative: str) -> Optional[EODReport]:
        return self.repo.update_narrative(db, report_id, narrative)

    def mark_posted(self, db: Session, report_id: int) -> Optional[EODReport]:
        return self.repo.mark_posted(db, report_id)

    def get_history(self, db: Session, limit: int = 30) -> list[EODReport]:
        return self.repo.get_history(db, limit)


report_service = ReportService()
```

### `app/services/teams_service.py`

```python
import httpx

from app.models.report import EODReport


class TeamsPoster:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def post(self, report: EODReport) -> bool:
        """Post an EOD report to Teams as an Adaptive Card."""
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": report.date.strftime("%B %#d, %Y"),
                                "weight": "Bolder",
                                "size": "Medium",
                            },
                            {
                                "type": "TextBlock",
                                "text": report.narrative,
                                "wrap": True,
                            },
                        ],
                    },
                }
            ],
        }

        response = httpx.post(self.webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        return True

    def test_connection(self) -> bool:
        """Send a test message to verify the webhook works."""
        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": "EOD Reporter - Connection Test",
                                "weight": "Bolder",
                            },
                            {
                                "type": "TextBlock",
                                "text": "Webhook is working correctly.",
                                "wrap": True,
                            },
                        ],
                    },
                }
            ],
        }
        try:
            response = httpx.post(self.webhook_url, json=payload, timeout=30)
            response.raise_for_status()
            return True
        except Exception:
            return False
```

---

## Step 6: LangGraph Agent

### `app/agent/state.py`

```python
from typing import TypedDict


class EODState(TypedDict):
    date: str                          # "2026-03-11"
    activities: list[dict]             # [{"content": "...", "time": "09:30", "period": "morning"}]
    grouped_activities: dict           # {"morning": [...], "afternoon": [...], "evening": [...]}
    draft: str                         # Current narrative draft
    review_feedback: str               # Feedback from self-review
    review_approved: bool              # Whether the review passed
    revision_count: int                # Number of revisions (cap at 2)
    final_narrative: str               # Approved narrative
```

### `app/agent/examples.json`

```json
[
    {
        "input": "Morning:\n- Weekly huddle meeting\n- Team huddle for Project 2 - discussed and delegated tasks\nAfternoon:\n- Tested workflow - monitored agent responses to different emails\n- Flagged notable responses to report back to team\n- Daily check-in with David and Matt for project updates\n- Developed FastAPI-based replacement for CloudConvert service (PDF to images)\n- Deployed it to Azure for use in n8n workflow",
        "output": "The day started with the weekly huddle followed by a team huddle for Project 2 where we discussed and delegated tasks for the day. From there, I moved into testing the workflow, monitoring how the agent responded to different emails, and flagging notable responses to report back to the team. We also had our daily check-in with David and Matt to catch up on project updates and stay aligned. Later in the day, I developed a FastAPI-based replacement for the temporary CloudConvert service that converts PDFs to images, and deployed it to Azure so it can be used directly in the n8n workflow."
    },
    {
        "input": "Morning:\n- Tried to automate the testing process - repetitive and time-consuming\n- Some configs need editing directly in n8n, making full automation hard\n- Connected Claude, Claude Code, and MCP into n8n workflow\nAfternoon:\n- Couldn't get automation working after a few hours\n- Shifted back to manual testing\n- Results mostly okay but some responses need improvement\n- Tested different scenarios and flagged areas for improvement",
        "output": "I started the morning by trying to automate the testing process since it's repetitive and time-consuming. However, some configurations need to be edited directly inside n8n, which made full automation quite challenging. I also connected and integrated Claude, Claude Code, and MCP into the n8n workflow on my machine to have Claude AI assist with the workflow. After spending a few hours on it, I wasn't able to get the automation working, so I shifted back to testing the agent manually. The results were mostly okay, but some responses still need improvement. The rest of the day was spent testing across different scenarios and flagging areas where the agent can do better so we can make those adjustments later."
    },
    {
        "input": "Morning:\n- Group huddle - went over yesterday's progress, delegated tasks\n- Assigned to test workflow: bookings, connote lookups, quotation requests\nAfternoon:\n- Agent handled all test cases well\n- Made adjustments to make workflow more stable\n- Christian provided Claude plan\n- Explored Claude capabilities for our workflow\nEvening:\n- Testing and logging agent responses\n- Compiled everything into Excel sheet for tracking",
        "output": "We started off the morning with a group huddle to go over yesterday's progress and delegate tasks for the day. I was assigned to test the workflow focusing on bookings, connote lookups, and quotation requests \u2014 and the agent handled all of them well. Throughout the day, we also made a lot of adjustments that made the workflow more stable across various cases. Later, Christian provided us with a Claude plan, so I took the opportunity to explore Claude's capabilities and how it could be used in our workflow. I wrapped up the day by testing and logging the agents' responses and compiling everything into an Excel sheet for tracking and review."
    }
]
```

### `app/agent/prompts.py`

```python
import json
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

# ──────────────────────────────────────────────
# System Prompt — [Role]+[Expertise]+[Guidelines]+[Output Format]+[Constraints]
# (from prompt-engineering-patterns skill)
# ──────────────────────────────────────────────

EOD_SYSTEM_PROMPT = """\
[Role]
You are a professional report writer specializing in End of Day (EOD) reports \
for software development teams.

[Expertise]
Your expertise is transforming raw daily activity notes into polished, \
narrative-style summaries that read naturally and professionally.

[Guidelines]
- Write in narrative paragraph format with chronological flow through the day
- Use a professional but conversational tone
- Mention meetings, tasks, challenges, and outcomes naturally
- Use transitions like "From there," "Later in the day," "After that"
- Start with how the day began and flow naturally through activities

[Output Format]
- 1-2 paragraphs, approximately 100-200 words
- Plain text only, no markdown formatting

[Constraints]
- Do NOT use bullet points, numbered lists, or markdown formatting
- Do NOT add a greeting, sign-off, or date header
- Do NOT fabricate details not present in the input
- Do NOT use overly formal or corporate language
- Keep it concise — no filler sentences"""

# ──────────────────────────────────────────────
# Review Prompt — Chain-of-Thought with Self-Verification
# (from prompt-engineering-patterns skill)
# ──────────────────────────────────────────────

REVIEW_SYSTEM_PROMPT = """\
[Role]
You are a quality reviewer for End of Day (EOD) reports.

[Expertise]
You evaluate whether generated reports meet specific style and quality standards.

[Guidelines]
Review the draft step by step against each criterion:

Step 1 - NARRATIVE FORMAT: Is it paragraph form? Any bullet points or numbered lists?
Step 2 - CHRONOLOGICAL FLOW: Does it follow morning to afternoon to evening order?
Step 3 - TONE: Professional but conversational? Not too formal, not too casual?
Step 4 - ACCURACY: Does it only mention activities from the input? Any fabricated details?
Step 5 - LENGTH: Is it 1-2 paragraphs, approximately 80-250 words?
Step 6 - TRANSITIONS: Does it use natural transitions between activities?

After evaluating all steps, decide whether to approve.

[Constraints]
- Only reject if a criterion is clearly violated
- Provide specific, actionable feedback when rejecting"""

# ──────────────────────────────────────────────
# Prompt Templates
# ──────────────────────────────────────────────

GENERATE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", EOD_SYSTEM_PROMPT),
    ("human",
     "Here are example EOD reports for reference on tone and style:\n\n"
     "{few_shot_examples}\n\n"
     "---\n\n"
     "Now transform these activity notes into a narrative EOD report:\n\n"
     "{activities_text}\n\n"
     "Write the EOD report narrative:"),
])

REVIEW_PROMPT = ChatPromptTemplate.from_messages([
    ("system", REVIEW_SYSTEM_PROMPT),
    ("human",
     "Original activity notes:\n{activities_text}\n\n"
     "Generated EOD report:\n{draft}\n\n"
     "Review this report against the criteria:"),
])

REVISE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", EOD_SYSTEM_PROMPT),
    ("human",
     "Here are example EOD reports for reference:\n\n"
     "{few_shot_examples}\n\n"
     "---\n\n"
     "Activity notes:\n{activities_text}\n\n"
     "Previous draft:\n{draft}\n\n"
     "Reviewer feedback:\n{feedback}\n\n"
     "Please revise the EOD report based on the feedback:"),
])


# ──────────────────────────────────────────────
# Few-Shot Examples (loaded from examples.json)
# ──────────────────────────────────────────────

_EXAMPLES_PATH = Path(__file__).parent / "examples.json"


def load_few_shot_examples() -> list[dict]:
    with open(_EXAMPLES_PATH, encoding="utf-8") as f:
        return json.load(f)


def format_few_shot_examples() -> str:
    """Format few-shot examples into a string for the prompt."""
    examples = load_few_shot_examples()
    parts = []
    for i, ex in enumerate(examples, 1):
        parts.append(f"Example {i}:\nInput:\n{ex['input']}\n\nOutput:\n{ex['output']}")
    return "\n\n---\n\n".join(parts)


def format_activities_for_prompt(grouped: dict) -> str:
    """Convert grouped activities dict into a formatted string for the prompt."""
    lines = []
    for period in ["morning", "afternoon", "evening"]:
        items = grouped.get(period, [])
        if items:
            lines.append(f"{period.capitalize()}:")
            for item in items:
                time_str = item.get("time", "")
                content = item.get("content", "")
                lines.append(f"- [{time_str}] {content}" if time_str else f"- {content}")
    return "\n".join(lines)
```

### `app/agent/nodes.py`

```python
from datetime import date

from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy.orm import Session

from app.agent.state import EODState
from app.agent.prompts import (
    GENERATE_PROMPT,
    REVIEW_PROMPT,
    REVISE_PROMPT,
    format_few_shot_examples,
    format_activities_for_prompt,
)
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.schemas.report import ReviewResult
from app.services.activity_service import activity_service


# ──────────────────────────────────────────────
# LLM Initialization (Gemini)
# ──────────────────────────────────────────────

_llm: ChatGoogleGenerativeAI | None = None


def get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        settings = get_settings()
        _llm = ChatGoogleGenerativeAI(
            model=settings.MODEL_NAME,
            max_output_tokens=1024,
        )
    return _llm


# ──────────────────────────────────────────────
# Node: Fetch activities from database
# ──────────────────────────────────────────────

def fetch_activities(state: EODState) -> dict:
    target_date = date.fromisoformat(state["date"])
    db: Session = SessionLocal()
    try:
        grouped = activity_service.get_grouped(db, target_date)

        activities_list = []
        grouped_dict = {}
        for period, items in grouped.items():
            period_list = []
            for a in items:
                entry = {
                    "content": a.content,
                    "time": a.logged_at.strftime("%H:%M"),
                    "period": a.effective_time_period.value,
                }
                activities_list.append(entry)
                period_list.append(entry)
            grouped_dict[period] = period_list

        return {
            "activities": activities_list,
            "grouped_activities": grouped_dict,
        }
    finally:
        db.close()


# ──────────────────────────────────────────────
# Node: Generate narrative draft
# ──────────────────────────────────────────────

def generate_draft(state: EODState) -> dict:
    llm = get_llm()
    chain = GENERATE_PROMPT | llm

    activities_text = format_activities_for_prompt(state["grouped_activities"])
    few_shot = format_few_shot_examples()

    response = chain.invoke({
        "few_shot_examples": few_shot,
        "activities_text": activities_text,
    })

    return {"draft": response.content.strip()}


# ──────────────────────────────────────────────
# Node: Self-review (structured output)
# ──────────────────────────────────────────────

def self_review(state: EODState) -> dict:
    llm = get_llm()
    activities_text = format_activities_for_prompt(state["grouped_activities"])

    try:
        # Use structured output — eliminates fragile string parsing
        structured_llm = llm.with_structured_output(ReviewResult)
        chain = REVIEW_PROMPT | structured_llm

        result: ReviewResult = chain.invoke({
            "activities_text": activities_text,
            "draft": state["draft"],
        })

        return {
            "review_feedback": result.feedback,
            "review_approved": result.approved,
            "revision_count": state.get("revision_count", 0) + (0 if result.approved else 1),
        }
    except Exception:
        # Fallback: accept the draft if structured output fails
        return {
            "review_feedback": "Review unavailable — accepting draft.",
            "review_approved": True,
            "revision_count": state.get("revision_count", 0),
        }


# ──────────────────────────────────────────────
# Node: Revise draft based on feedback
# ──────────────────────────────────────────────

def revise_draft(state: EODState) -> dict:
    llm = get_llm()
    chain = REVISE_PROMPT | llm

    activities_text = format_activities_for_prompt(state["grouped_activities"])
    few_shot = format_few_shot_examples()

    response = chain.invoke({
        "few_shot_examples": few_shot,
        "activities_text": activities_text,
        "draft": state["draft"],
        "feedback": state["review_feedback"],
    })

    return {"draft": response.content.strip()}
```

### `app/agent/graph.py`

```python
from langgraph.graph import StateGraph, END

from app.agent.state import EODState
from app.agent.nodes import (
    fetch_activities,
    generate_draft,
    self_review,
    revise_draft,
)


def should_revise(state: EODState) -> str:
    """Conditional edge: revise or finalize."""
    if state.get("review_approved", False):
        return "finalize"
    if state.get("revision_count", 0) >= 2:
        return "finalize"
    return "revise"


def finalize(state: EODState) -> dict:
    """Copy approved draft to final_narrative."""
    return {"final_narrative": state["draft"]}


def build_eod_graph() -> StateGraph:
    graph = StateGraph(EODState)

    # Add nodes
    graph.add_node("fetch_activities", fetch_activities)
    graph.add_node("generate_draft", generate_draft)
    graph.add_node("self_review", self_review)
    graph.add_node("revise_draft", revise_draft)
    graph.add_node("finalize", finalize)

    # Define edges
    graph.set_entry_point("fetch_activities")
    graph.add_edge("fetch_activities", "generate_draft")
    graph.add_edge("generate_draft", "self_review")

    # Conditional: review passes → finalize, fails → revise (cap at 2)
    graph.add_conditional_edges(
        "self_review",
        should_revise,
        {
            "finalize": "finalize",
            "revise": "revise_draft",
        },
    )
    graph.add_edge("revise_draft", "self_review")
    graph.add_edge("finalize", END)

    return graph.compile()


# Pre-compiled graph instance
eod_agent = build_eod_graph()
```

---

## Step 7: API Layer

### `app/api/dependencies.py`

```python
from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.teams_service import TeamsPoster


def get_teams_poster(settings: Settings = Depends(get_settings)) -> TeamsPoster:
    return TeamsPoster(settings.TEAMS_WEBHOOK_URL)
```

### `app/api/v1/router.py`

```python
from fastapi import APIRouter

from app.api.v1.endpoints import activities, reports, pages

api_router = APIRouter()
api_router.include_router(activities.router, prefix="/activities", tags=["activities"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(pages.router, tags=["pages"])
```

### `app/api/v1/endpoints/activities.py`

```python
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
```

### `app/api/v1/endpoints/reports.py`

```python
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
        raise HTTPException(status_code=400, detail="No activities logged for this date")

    result = eod_agent.invoke({
        "date": target.isoformat(),
        "activities": [],
        "grouped_activities": {},
        "draft": "",
        "review_feedback": "",
        "review_approved": False,
        "revision_count": 0,
        "final_narrative": "",
    })

    narrative = result.get("final_narrative", result.get("draft", ""))
    report = report_service.save(db, target, narrative)

    return RedirectResponse(url=f"/reports/preview?target_date={target}", status_code=303)


@router.post("/{report_id}/update")
def update_narrative(
    report_id: int,
    narrative: str = Form(...),
    db: Session = Depends(get_db),
):
    report = report_service.update_narrative(db, report_id, narrative)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return RedirectResponse(url=f"/reports/preview?target_date={report.date}", status_code=303)


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
    return RedirectResponse(url=f"/reports/preview?target_date={report.date}", status_code=303)
```

### `app/api/v1/endpoints/pages.py`

```python
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.activity_service import activity_service
from app.services.report_service import report_service

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    grouped = activity_service.get_grouped(db, today)
    all_activities = activity_service.get_by_date(db, today)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "today": today,
            "grouped_activities": grouped,
            "has_activities": len(all_activities) > 0,
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
```

---

## Step 8: Templates + Static

### `app/templates/base.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}EOD Reporter{% endblock %}</title>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <nav>
        <div class="nav-content">
            <a href="/" class="logo">EOD Reporter</a>
            <div class="nav-links">
                <a href="/">Dashboard</a>
                <a href="/reports/history">History</a>
            </div>
        </div>
    </nav>
    <main>
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

### `app/templates/dashboard.html`

```html
{% extends "base.html" %}
{% block title %}Dashboard - EOD Reporter{% endblock %}

{% block content %}
<h1>{{ today.strftime("%B %#d, %Y") }}</h1>

<!-- Quick Log Form -->
<section class="card">
    <h2>Log Activity</h2>
    <form method="post" action="/activities/log" class="log-form">
        <input
            type="text"
            name="content"
            placeholder="What did you just do? (e.g., 'Had team huddle for Project 2')"
            required
            autofocus
        >
        <button type="submit">Log</button>
    </form>
</section>

<!-- Today's Activities -->
<section class="card">
    <h2>Today's Activities</h2>

    {% for period in ["morning", "afternoon", "evening"] %}
    <div class="time-group">
        <h3>{{ period | capitalize }}</h3>
        {% if grouped_activities[period] %}
            {% for activity in grouped_activities[period] %}
            <div class="activity-item">
                <span class="time-badge">{{ activity.logged_at.strftime("%H:%M") }}</span>
                <span class="activity-content">{{ activity.content }}</span>
                <div class="activity-actions">
                    <button class="btn-delete" title="Delete"
                            hx-delete="/activities/{{ activity.id }}"
                            hx-target="closest .activity-item"
                            hx-swap="outerHTML"
                            hx-confirm="Delete this activity?">x</button>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p class="empty">No activities logged</p>
        {% endif %}
    </div>
    {% endfor %}
</section>

<!-- Generate EOD -->
<section class="card">
    <h2>Generate EOD Report</h2>
    <form method="post" action="/reports/generate">
        <button type="submit" class="btn-primary" {% if not has_activities %}disabled{% endif %}>
            Generate Report
        </button>
        {% if not has_activities %}
        <p class="hint">Log some activities first before generating a report.</p>
        {% endif %}
    </form>
</section>
{% endblock %}
```

### `app/templates/preview.html`

```html
{% extends "base.html" %}
{% block title %}Preview - EOD Reporter{% endblock %}

{% block content %}
<h1>EOD Preview - {{ target_date.strftime("%B %#d, %Y") }}</h1>

{% if report %}
<section class="card">
    <div class="status-badge status-{{ report.status.value }}">
        {{ report.status.value | upper }}
    </div>

    <div class="preview-box">
        <h3>{{ target_date.strftime("%B %#d, %Y") }}</h3>
        <p>{{ report.narrative }}</p>
    </div>

    {% if report.status.value != "posted" %}
    <details>
        <summary>Edit narrative</summary>
        <form method="post" action="/reports/{{ report.id }}/update">
            <textarea name="narrative" rows="8">{{ report.narrative }}</textarea>
            <button type="submit">Save Changes</button>
        </form>
    </details>

    <form method="post" action="/reports/{{ report.id }}/post-to-teams" class="post-form">
        <button type="submit" class="btn-primary btn-post"
                onclick="return confirm('Post this EOD to Teams?')">
            Post to Teams
        </button>
    </form>
    {% else %}
    <p class="posted-notice">
        Posted to Teams at {{ report.posted_at.strftime("%H:%M on %B %#d, %Y") }}
    </p>
    {% endif %}

    <form method="post" action="/reports/generate?target_date={{ target_date.isoformat() }}">
        <button type="submit" class="btn-secondary">Regenerate</button>
    </form>
</section>
{% else %}
<section class="card">
    <p>No report generated for this date yet.</p>
    <a href="/" class="btn-primary">Go to Dashboard</a>
</section>
{% endif %}
{% endblock %}
```

### `app/templates/history.html`

```html
{% extends "base.html" %}
{% block title %}History - EOD Reporter{% endblock %}

{% block content %}
<h1>Report History</h1>

{% if reports %}
{% for report in reports %}
<section class="card history-card">
    <div class="history-header">
        <h3>{{ report.date.strftime("%B %#d, %Y") }}</h3>
        <span class="status-badge status-{{ report.status.value }}">
            {{ report.status.value }}
        </span>
    </div>
    <p>{{ report.narrative }}</p>
    <div class="history-meta">
        Generated: {{ report.generated_at.strftime("%H:%M") }}
        {% if report.posted_at %}
        &middot; Posted: {{ report.posted_at.strftime("%H:%M") }}
        {% endif %}
    </div>
</section>
{% endfor %}
{% else %}
<section class="card">
    <p>No reports yet. Start logging activities and generate your first EOD!</p>
</section>
{% endif %}
{% endblock %}
```

### `app/static/style.css`

```css
/* ── Reset & Base ── */
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f5f5f5;
    color: #333;
    line-height: 1.6;
}

/* ── Navigation ── */
nav {
    background: #1a1a2e;
    color: white;
    padding: 1rem 0;
}
.nav-content {
    max-width: 800px;
    margin: 0 auto;
    padding: 0 1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.logo { color: white; text-decoration: none; font-weight: 700; font-size: 1.2rem; }
.nav-links a { color: #aaa; text-decoration: none; margin-left: 1.5rem; }
.nav-links a:hover { color: white; }

/* ── Main Content ── */
main {
    max-width: 800px;
    margin: 2rem auto;
    padding: 0 1rem;
}
h1 { margin-bottom: 1.5rem; color: #1a1a2e; }

/* ── Cards ── */
.card {
    background: white;
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.card h2 { margin-bottom: 1rem; font-size: 1.1rem; color: #555; }

/* ── Log Form ── */
.log-form { display: flex; gap: 0.5rem; }
.log-form input {
    flex: 1;
    padding: 0.75rem 1rem;
    border: 2px solid #e0e0e0;
    border-radius: 6px;
    font-size: 1rem;
}
.log-form input:focus { outline: none; border-color: #4a6cf7; }
.log-form button {
    padding: 0.75rem 1.5rem;
    background: #4a6cf7;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 1rem;
}
.log-form button:hover { background: #3a5ce5; }

/* ── Time Groups ── */
.time-group { margin-bottom: 1rem; }
.time-group h3 {
    font-size: 0.85rem;
    text-transform: uppercase;
    color: #888;
    margin-bottom: 0.5rem;
    letter-spacing: 0.05em;
}
.activity-item {
    display: flex;
    align-items: center;
    padding: 0.5rem 0;
    border-bottom: 1px solid #f0f0f0;
    gap: 0.75rem;
}
.time-badge {
    background: #e8ecff;
    color: #4a6cf7;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 600;
    white-space: nowrap;
}
.activity-content { flex: 1; }
.btn-delete {
    background: none;
    border: none;
    color: #ccc;
    cursor: pointer;
    font-size: 1rem;
    padding: 0.25rem;
}
.btn-delete:hover { color: #e74c3c; }

/* ── Buttons ── */
.btn-primary {
    display: inline-block;
    padding: 0.75rem 2rem;
    background: #4a6cf7;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 1rem;
    text-decoration: none;
}
.btn-primary:hover { background: #3a5ce5; }
.btn-primary:disabled { background: #ccc; cursor: not-allowed; }
.btn-secondary {
    padding: 0.5rem 1rem;
    background: #e0e0e0;
    color: #555;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.9rem;
}
.btn-secondary:hover { background: #d0d0d0; }
.btn-post { background: #27ae60; }
.btn-post:hover { background: #219a52; }

/* ── Preview ── */
.preview-box {
    background: #fafafa;
    border-left: 4px solid #4a6cf7;
    padding: 1.5rem;
    margin: 1rem 0;
    border-radius: 0 6px 6px 0;
}
.preview-box h3 { margin-bottom: 0.75rem; }
.preview-box p { line-height: 1.8; }

textarea {
    width: 100%;
    padding: 1rem;
    border: 2px solid #e0e0e0;
    border-radius: 6px;
    font-size: 1rem;
    font-family: inherit;
    line-height: 1.6;
    resize: vertical;
    margin: 0.5rem 0;
}
textarea:focus { outline: none; border-color: #4a6cf7; }

details { margin: 1rem 0; }
details summary {
    cursor: pointer;
    color: #4a6cf7;
    font-weight: 500;
}

/* ── Status Badges ── */
.status-badge {
    display: inline-block;
    padding: 0.2rem 0.75rem;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
}
.status-draft { background: #fff3cd; color: #856404; }
.status-confirmed { background: #d1ecf1; color: #0c5460; }
.status-posted { background: #d4edda; color: #155724; }

/* ── History ── */
.history-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
.history-meta { margin-top: 0.75rem; font-size: 0.8rem; color: #888; }
.posted-notice { color: #27ae60; font-weight: 500; margin: 1rem 0; }

/* ── Misc ── */
.empty { color: #bbb; font-style: italic; }
.hint { color: #888; font-size: 0.85rem; margin-top: 0.5rem; }
.post-form { margin: 1rem 0; }
```

---

## Step 9: Main App + Scheduler

### `app/main.py`

```python
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
        result = eod_agent.invoke({
            "date": today.isoformat(),
            "activities": [],
            "grouped_activities": {},
            "draft": "",
            "review_feedback": "",
            "review_approved": False,
            "revision_count": 0,
            "final_narrative": "",
        })
        narrative = result.get("final_narrative", result.get("draft", ""))
        report_service.save(db, today, narrative)
        print(f"[Scheduler] EOD draft saved. Visit /reports/preview to review and post.")
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
```

---

## Step 10: CLI

### `app/cli.py`

```python
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from datetime import date

from app.core.config import get_settings
from app.core.database import init_db, SessionLocal
from app.models.activity import TimePeriod
from app.services.activity_service import activity_service
from app.services.report_service import report_service
from app.services.teams_service import TeamsPoster
from app.agent.graph import eod_agent

load_dotenv()
init_db()

app = typer.Typer(help="EOD Reporter - Log activities and generate End of Day reports")
console = Console()


@app.command()
def log(
    content: str = typer.Argument(..., help="What you did"),
    time: str = typer.Option(None, "--time", "-t", help="Override: morning, afternoon, evening"),
):
    """Log an activity with the current timestamp."""
    db = SessionLocal()
    try:
        override = TimePeriod(time) if time else None
        activity = activity_service.log_activity(db, content=content, time_period_override=override)
        period = activity.effective_time_period.value
        console.print(
            f"[green]>[/green] Logged at {activity.logged_at.strftime('%H:%M')} "
            f"[dim]({period})[/dim]: {content}"
        )
    finally:
        db.close()


@app.command(name="list")
def list_activities(
    target_date: str = typer.Option(None, "--date", "-d", help="YYYY-MM-DD, defaults to today"),
):
    """Show today's logged activities grouped by time period."""
    db = SessionLocal()
    try:
        d = date.fromisoformat(target_date) if target_date else date.today()
        grouped = activity_service.get_grouped(db, d)

        table = Table(title=f"Activities - {d.strftime('%B %#d, %Y')}")
        table.add_column("Time", style="cyan", width=8)
        table.add_column("Period", style="dim", width=12)
        table.add_column("Activity")

        for period in ["morning", "afternoon", "evening"]:
            for a in grouped[period]:
                table.add_row(
                    a.logged_at.strftime("%H:%M"),
                    period.capitalize(),
                    a.content,
                )

        total = sum(len(v) for v in grouped.values())
        console.print(table)
        console.print(f"\n[dim]Total: {total} activities[/dim]")
    finally:
        db.close()


@app.command()
def compile(
    target_date: str = typer.Option(None, "--date", "-d", help="YYYY-MM-DD, defaults to today"),
):
    """Generate an EOD report using the LangGraph agent."""
    db = SessionLocal()
    try:
        d = date.fromisoformat(target_date) if target_date else date.today()
        grouped = activity_service.get_grouped(db, d)

        total = sum(len(v) for v in grouped.values())
        if total == 0:
            console.print("[yellow]No activities logged for this date.[/yellow]")
            raise typer.Exit(1)

        console.print(f"\n[bold blue]Generating EOD for {d.strftime('%B %#d, %Y')}...[/bold blue]")

        result = eod_agent.invoke({
            "date": d.isoformat(),
            "activities": [],
            "grouped_activities": {},
            "draft": "",
            "review_feedback": "",
            "review_approved": False,
            "revision_count": 0,
            "final_narrative": "",
        })

        narrative = result.get("final_narrative", result.get("draft", ""))
        report = report_service.save(db, d, narrative)

        console.print(Panel(
            narrative,
            title=f"EOD Report - {d.strftime('%B %#d, %Y')}",
            border_style="green",
        ))
        console.print(f"[dim]Word count: {len(narrative.split())}[/dim]")
        console.print(f"[dim]Report saved as draft (ID: {report.id})[/dim]")
        console.print(
            f"\n[bold]Open http://localhost:8000/reports/preview?target_date={d} to review and post.[/bold]"
        )
    finally:
        db.close()


@app.command()
def post(
    target_date: str = typer.Option(None, "--date", "-d", help="YYYY-MM-DD, defaults to today"),
):
    """Post the latest report to Teams."""
    db = SessionLocal()
    try:
        d = date.fromisoformat(target_date) if target_date else date.today()
        report = report_service.get_by_date(db, d)

        if not report:
            console.print("[yellow]No report found. Run 'compile' first.[/yellow]")
            raise typer.Exit(1)

        console.print(Panel(report.narrative, title="Report to post", border_style="blue"))

        confirm = typer.confirm("Post this to Teams?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()

        settings = get_settings()
        poster = TeamsPoster(settings.TEAMS_WEBHOOK_URL)
        poster.post(report)
        report_service.mark_posted(db, report.id)
        console.print("[bold green]Posted to Teams![/bold green]")
    finally:
        db.close()


@app.command()
def test_webhook():
    """Test the Teams webhook connection."""
    settings = get_settings()
    poster = TeamsPoster(settings.TEAMS_WEBHOOK_URL)
    if poster.test_connection():
        console.print("[bold green]Webhook is working! Check your Teams channel.[/bold green]")
    else:
        console.print("[bold red]Webhook test failed. Check the URL in .env.[/bold red]")


if __name__ == "__main__":
    app()
```

---

## Running the App

### Start the web server

```bash
cd "c:\Users\Jansen Cruz\Desktop\Jansen\internity"

uv run uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

### Use the CLI (separate terminal)

```bash
cd "c:\Users\Jansen Cruz\Desktop\Jansen\internity"

# Log activities throughout the day
uv run eod log "Had weekly team huddle"
uv run eod log "Team huddle for Project 2 - discussed and delegated tasks"
uv run eod log "Tested workflow - monitored agent responses to emails"
uv run eod log "Daily check-in with David and Matt" --time afternoon
uv run eod log "Worked on PDF conversion service" --time afternoon

# View today's activities
uv run eod list

# Generate EOD report
uv run eod compile

# Post to Teams (from CLI)
uv run eod post

# Test webhook connection
uv run eod test-webhook
```

---

## Quick Reference

| Action | CLI | Web |
|---|---|---|
| Log activity | `uv run eod log "text"` | Dashboard: type and submit |
| Log with time override | `uv run eod log "text" --time morning` | Dashboard: edit dropdown |
| View activities | `uv run eod list` | Dashboard |
| Generate EOD | `uv run eod compile` | Dashboard: "Generate Report" |
| Preview EOD | Browser link after compile | `/reports/preview` |
| Edit EOD | Web only | Preview: "Edit narrative" |
| Post to Teams | `uv run eod post` | Preview: "Post to Teams" |
| View history | Web only | `/reports/history` |
| Test webhook | `uv run eod test-webhook` | - |

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `GOOGLE_API_KEY not set` | Make sure `.env` exists with your key from aistudio.google.com |
| `TEAMS_WEBHOOK_URL not set` | Add your webhook URL to `.env` |
| Webhook returns 400/403 | Recreate the webhook in Teams Workflows app |
| `ModuleNotFoundError` | Run `uv sync` to install dependencies |
| Database errors | Delete `eod_reporter.db` and restart (tables recreated automatically) |
| LLM returns bullet points | Self-review should catch this; if persistent, add more examples to `examples.json` |
| Structured output parsing fails | The fallback in `self_review` accepts the draft; check Gemini model availability |
| `strftime %#d` not working | `%#d` is Windows-specific (no leading zero). On Linux/Mac use `%-d` instead |

---

## What's Next (Optional Enhancements)

- **Desktop notifications** when scheduler generates a draft (use `plyer` or `win10toast`)
- **Add more few-shot examples** over time from your best EODs to `examples.json`
- **Weekly summary** agent that compiles all EODs from the week
- **Docker deployment** for always-on access
- **Slack integration** as alternative to Teams
