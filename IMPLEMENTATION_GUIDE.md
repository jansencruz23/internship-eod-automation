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
                    2. group_by_time      → morning / afternoon / evening
                    3. generate_draft     → Claude writes narrative EOD
                    4. self_review        → Claude checks quality
                    5. (loop if needed)   → revise up to 2 times
                    6. return draft       → user previews + confirms
                    7. post_to_teams      → Adaptive Card via webhook
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Package Manager | **uv** |
| LLM Orchestration | **LangGraph** + **LangChain** |
| LLM | **Claude Sonnet 4** via `langchain-anthropic` |
| Web Interface | **FastAPI** + **Jinja2** + **HTMX** |
| CLI | **Typer** + **Rich** |
| Database | **SQLite** via **SQLAlchemy** |
| Scheduler | **APScheduler** |
| Teams Posting | **Teams Workflows Webhook** (HTTP POST with Adaptive Card) |
| HTTP Client | **httpx** |

---

## Project Structure

```
internity/
├── .agents/skills/                    # (existing — unchanged)
├── eod_reporter/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app + APScheduler
│   ├── cli.py                         # Typer CLI
│   ├── models.py                      # SQLAlchemy + Pydantic models
│   ├── database.py                    # SQLite connection
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── graph.py                   # LangGraph state graph
│   │   ├── nodes.py                   # Graph node functions
│   │   ├── state.py                   # TypedDict state schema
│   │   └── prompts.py                 # Prompt templates + few-shot examples
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── activities.py              # Activity CRUD routes
│   │   └── reports.py                 # EOD report routes
│   ├── services/
│   │   ├── __init__.py
│   │   ├── activity_service.py        # Activity business logic
│   │   ├── report_service.py          # Report generation orchestration
│   │   └── teams_poster.py            # Teams webhook integration
│   ├── templates/
│   │   ├── base.html                  # Base layout
│   │   ├── dashboard.html             # Activity logging + today's view
│   │   ├── preview.html               # EOD preview + edit + post
│   │   └── history.html               # Past reports
│   └── static/
│       └── style.css
├── .env
├── .env.example
├── .gitignore
└── pyproject.toml
```

---

## Step 0: Prerequisites

### Install uv (if not already installed)

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip
pip install uv
```

### Set up Teams Webhook (one-time)

1. Open Microsoft Teams → go to your target channel
2. Click the **`...`** menu on the channel → select **"Workflows"**
3. Search for **"Post to a channel when a webhook request is received"**
4. Name it `EOD Report Webhook`, select your team and channel
5. Click **Create** → copy the generated webhook URL
6. Save this URL — you'll need it for `.env`

### Get an Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an API key
3. Save it — you'll need it for `.env`

---

## Step 1: Project Setup

### Initialize the project with uv

```bash
cd "c:\Users\Jansen Cruz\Desktop\Jansen\internity"

# Initialize uv project
uv init --no-readme

# Add all dependencies
uv add langchain-anthropic langchain-core langgraph
uv add fastapi uvicorn jinja2 python-multipart
uv add typer rich
uv add sqlalchemy
uv add httpx
uv add python-dotenv pydantic pydantic-settings
uv add apscheduler
```

### Create the folder structure

```bash
# Create all directories
mkdir -p eod_reporter/agent
mkdir -p eod_reporter/routers
mkdir -p eod_reporter/services
mkdir -p eod_reporter/templates
mkdir -p eod_reporter/static

# Create all __init__.py files
touch eod_reporter/__init__.py
touch eod_reporter/agent/__init__.py
touch eod_reporter/routers/__init__.py
touch eod_reporter/services/__init__.py
```

### Create `.env.example`

```ini
# .env.example — Copy this to .env and fill in your values

ANTHROPIC_API_KEY=sk-ant-xxxxx
TEAMS_WEBHOOK_URL=https://xxxxx.webhook.office.com/webhookb2/xxxxx
EOD_SCHEDULE_TIME=17:00
MODEL_NAME=claude-sonnet-4-6
```

### Create `.env`

```ini
# .env — Fill in your actual values

ANTHROPIC_API_KEY=your-actual-api-key-here
TEAMS_WEBHOOK_URL=your-actual-webhook-url-here
EOD_SCHEDULE_TIME=17:00
MODEL_NAME=claude-sonnet-4-6
```

### Create `.gitignore`

```gitignore
# .gitignore
.env
__pycache__/
*.pyc
*.db
.venv/
```

---

## Step 2: Database Layer

### `eod_reporter/database.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from pathlib import Path

DATABASE_PATH = Path(__file__).parent.parent / "eod_reporter.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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

### `eod_reporter/models.py`

```python
from datetime import date, datetime
from enum import Enum as PyEnum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Enum
from sqlalchemy.sql import func

from eod_reporter.database import Base


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class TimePeriod(str, PyEnum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class ReportStatus(str, PyEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    POSTED = "posted"


# ──────────────────────────────────────────────
# SQLAlchemy Models (Database Tables)
# ──────────────────────────────────────────────

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
        """Auto-categorize based on hour: morning < 12, afternoon 12-17, evening >= 17."""
        hour = dt.hour
        if hour < 12:
            return TimePeriod.MORNING
        elif hour < 17:
            return TimePeriod.AFTERNOON
        else:
            return TimePeriod.EVENING

    @property
    def effective_time_period(self) -> TimePeriod:
        """Return override if set, otherwise the auto-computed period."""
        return self.time_period_override or self.time_period


class EODReport(Base):
    __tablename__ = "eod_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, unique=True, nullable=False)
    narrative = Column(Text, nullable=False)
    status = Column(Enum(ReportStatus), default=ReportStatus.DRAFT, nullable=False)
    generated_at = Column(DateTime, default=func.now(), nullable=False)
    posted_at = Column(DateTime, nullable=True)


# ──────────────────────────────────────────────
# Pydantic Schemas (API Request/Response)
# ──────────────────────────────────────────────

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
```

---

## Step 3: Services Layer

### `eod_reporter/services/activity_service.py`

```python
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from eod_reporter.models import Activity, TimePeriod, ActivityCreate


def log_activity(
    db: Session,
    content: str,
    time_period_override: Optional[TimePeriod] = None,
) -> Activity:
    """Log a new activity with auto-computed time period."""
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


def get_activities_by_date(db: Session, target_date: date) -> list[Activity]:
    """Get all activities for a given date, ordered by time."""
    return (
        db.query(Activity)
        .filter(Activity.date == target_date)
        .order_by(Activity.logged_at)
        .all()
    )


def get_activities_grouped(db: Session, target_date: date) -> dict[str, list[Activity]]:
    """Get activities grouped by effective time period."""
    activities = get_activities_by_date(db, target_date)
    grouped = {"morning": [], "afternoon": [], "evening": []}
    for a in activities:
        period = a.effective_time_period.value
        grouped[period].append(a)
    return grouped


def update_activity(db: Session, activity_id: int, **kwargs) -> Optional[Activity]:
    """Update an activity's content or time period override."""
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        return None
    for key, value in kwargs.items():
        if value is not None:
            setattr(activity, key, value)
    db.commit()
    db.refresh(activity)
    return activity


def delete_activity(db: Session, activity_id: int) -> bool:
    """Delete an activity. Returns True if deleted."""
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        return False
    db.delete(activity)
    db.commit()
    return True
```

### `eod_reporter/services/teams_poster.py`

```python
import httpx
from datetime import date

from eod_reporter.models import EODReport


class TeamsPoster:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def post(self, report: EODReport) -> bool:
        """Post an EOD report to Teams via Workflows webhook as an Adaptive Card."""
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
                                "text": report.date.strftime("%B %-d, %Y"),
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
        test_payload = {
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
                                "text": "EOD Reporter — Connection Test",
                                "weight": "Bolder",
                            },
                            {
                                "type": "TextBlock",
                                "text": "If you see this message, the webhook is working correctly.",
                                "wrap": True,
                            },
                        ],
                    },
                }
            ],
        }
        try:
            response = httpx.post(self.webhook_url, json=test_payload, timeout=30)
            response.raise_for_status()
            return True
        except Exception:
            return False
```

### `eod_reporter/services/report_service.py`

```python
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from eod_reporter.models import EODReport, ReportStatus


def get_report_by_date(db: Session, target_date: date) -> Optional[EODReport]:
    """Get an EOD report for a specific date."""
    return db.query(EODReport).filter(EODReport.date == target_date).first()


def save_report(db: Session, target_date: date, narrative: str) -> EODReport:
    """Save or update an EOD report draft."""
    report = get_report_by_date(db, target_date)
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


def update_report_narrative(db: Session, report_id: int, narrative: str) -> Optional[EODReport]:
    """Update the narrative of an existing report."""
    report = db.query(EODReport).filter(EODReport.id == report_id).first()
    if not report:
        return None
    report.narrative = narrative
    db.commit()
    db.refresh(report)
    return report


def mark_posted(db: Session, report_id: int) -> Optional[EODReport]:
    """Mark a report as posted."""
    report = db.query(EODReport).filter(EODReport.id == report_id).first()
    if not report:
        return None
    report.status = ReportStatus.POSTED
    report.posted_at = datetime.now()
    db.commit()
    db.refresh(report)
    return report


def get_report_history(db: Session, limit: int = 30) -> list[EODReport]:
    """Get recent EOD reports."""
    return (
        db.query(EODReport)
        .order_by(EODReport.date.desc())
        .limit(limit)
        .all()
    )
```

---

## Step 4: LangGraph Agent

### `eod_reporter/agent/state.py`

```python
from typing import TypedDict


class EODState(TypedDict):
    date: str                          # "2026-03-11"
    activities: list[dict]             # [{"content": "...", "time": "09:30", "period": "morning"}, ...]
    grouped_activities: dict           # {"morning": [...], "afternoon": [...], "evening": [...]}
    draft: str                         # Current narrative draft
    review_feedback: str               # Feedback from self-review
    review_approved: bool              # Whether the review passed
    revision_count: int                # Number of revisions so far (cap at 2)
    final_narrative: str               # Approved narrative
```

### `eod_reporter/agent/prompts.py`

```python
from langchain_core.prompts import ChatPromptTemplate

# ──────────────────────────────────────────────
# System Prompt — Defines the writing style
# ──────────────────────────────────────────────

EOD_SYSTEM_PROMPT = """\
You are a professional report writer who transforms daily activity notes \
into polished, narrative-style End of Day (EOD) reports.

Your writing style:
- Narrative paragraph format (NOT bullet points)
- Chronological flow through the day
- Professional but conversational tone
- Mentions meetings, tasks worked on, challenges, and outcomes naturally
- 1-2 paragraphs, approximately 100-200 words
- Starts with how the day began and flows naturally through activities
- Uses transitions like "From there," "Later in the day," "After that," "The rest of the day"

Constraints:
- Do NOT use bullet points, numbered lists, or markdown formatting
- Do NOT add a greeting, sign-off, or date header
- Do NOT fabricate details not present in the input
- Do NOT use overly formal or corporate language
- Keep it concise — no filler sentences"""

# ──────────────────────────────────────────────
# Few-Shot Examples — Real EODs for style reference
# ──────────────────────────────────────────────

FEW_SHOT_EXAMPLES = [
    {
        "input": (
            "Morning:\n"
            "- Weekly huddle meeting\n"
            "- Team huddle for Project 2 - discussed and delegated tasks\n"
            "Afternoon:\n"
            "- Tested workflow - monitored agent responses to different emails\n"
            "- Flagged notable responses to report back to team\n"
            "- Daily check-in with David and Matt for project updates\n"
            "- Developed FastAPI-based replacement for CloudConvert service (PDF to images)\n"
            "- Deployed it to Azure for use in n8n workflow"
        ),
        "output": (
            "The day started with the weekly huddle followed by a team huddle for "
            "Project 2 where we discussed and delegated tasks for the day. From there, "
            "I moved into testing the workflow, monitoring how the agent responded to "
            "different emails, and flagging notable responses to report back to the team. "
            "We also had our daily check-in with David and Matt to catch up on project "
            "updates and stay aligned. Later in the day, I developed a FastAPI-based "
            "replacement for the temporary CloudConvert service that converts PDFs to "
            "images, and deployed it to Azure so it can be used directly in the n8n workflow."
        ),
    },
    {
        "input": (
            "Morning:\n"
            "- Tried to automate the testing process - repetitive and time-consuming\n"
            "- Some configs need editing directly in n8n, making full automation hard\n"
            "- Connected Claude, Claude Code, and MCP into n8n workflow\n"
            "Afternoon:\n"
            "- Couldn't get automation working after a few hours\n"
            "- Shifted back to manual testing\n"
            "- Results mostly okay but some responses need improvement\n"
            "- Tested different scenarios and flagged areas for improvement"
        ),
        "output": (
            "I started the morning by trying to automate the testing process since it's "
            "repetitive and time-consuming. However, some configurations need to be edited "
            "directly inside n8n, which made full automation quite challenging. I also "
            "connected and integrated Claude, Claude Code, and MCP into the n8n workflow "
            "on my machine to have Claude AI assist with the workflow. After spending a "
            "few hours on it, I wasn't able to get the automation working, so I shifted "
            "back to testing the agent manually. The results were mostly okay, but some "
            "responses still need improvement. The rest of the day was spent testing across "
            "different scenarios and flagging areas where the agent can do better so we "
            "can make those adjustments later."
        ),
    },
    {
        "input": (
            "Morning:\n"
            "- Group huddle - went over yesterday's progress, delegated tasks\n"
            "- Assigned to test workflow: bookings, connote lookups, quotation requests\n"
            "Afternoon:\n"
            "- Agent handled all test cases well\n"
            "- Made adjustments to make workflow more stable\n"
            "- Christian provided Claude plan\n"
            "- Explored Claude capabilities for our workflow\n"
            "Evening:\n"
            "- Testing and logging agent responses\n"
            "- Compiled everything into Excel sheet for tracking"
        ),
        "output": (
            "We started off the morning with a group huddle to go over yesterday's "
            "progress and delegate tasks for the day. I was assigned to test the workflow "
            "focusing on bookings, connote lookups, and quotation requests — and the agent "
            "handled all of them well. Throughout the day, we also made a lot of adjustments "
            "that made the workflow more stable across various cases. Later, Christian "
            "provided us with a Claude plan, so I took the opportunity to explore Claude's "
            "capabilities and how it could be used in our workflow. I wrapped up the day by "
            "testing and logging the agents' responses and compiling everything into an "
            "Excel sheet for tracking and review."
        ),
    },
]

# ──────────────────────────────────────────────
# Generation Prompt
# ──────────────────────────────────────────────

GENERATE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EOD_SYSTEM_PROMPT),
        (
            "human",
            "Here are example EOD reports for reference on tone and style:\n\n"
            "{few_shot_examples}\n\n"
            "---\n\n"
            "Now transform these activity notes into a narrative EOD report:\n\n"
            "{activities_text}\n\n"
            "Write the EOD report narrative:",
        ),
    ]
)

# ──────────────────────────────────────────────
# Self-Review Prompt
# ──────────────────────────────────────────────

REVIEW_SYSTEM_PROMPT = """\
You are a quality reviewer for End of Day (EOD) reports. You check whether a \
generated report meets the required style and quality standards.

Review criteria:
1. NARRATIVE FORMAT: Must be paragraph form. Reject if it uses bullet points or numbered lists.
2. CHRONOLOGICAL FLOW: Should follow the order of the day (morning → afternoon → evening).
3. TONE: Professional but conversational. Not too formal, not too casual.
4. ACCURACY: Must only mention activities from the input. No fabricated details.
5. LENGTH: Should be 1-2 paragraphs, approximately 80-250 words.
6. TRANSITIONS: Should use natural transitions between activities.

Respond in this exact format:
APPROVED: yes/no
FEEDBACK: <specific feedback if not approved, or "Looks good" if approved>"""

REVIEW_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", REVIEW_SYSTEM_PROMPT),
        (
            "human",
            "Original activity notes:\n{activities_text}\n\n"
            "Generated EOD report:\n{draft}\n\n"
            "Review this report against the criteria:",
        ),
    ]
)

# ──────────────────────────────────────────────
# Revision Prompt (used when self-review rejects)
# ──────────────────────────────────────────────

REVISE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", EOD_SYSTEM_PROMPT),
        (
            "human",
            "Here are example EOD reports for reference:\n\n"
            "{few_shot_examples}\n\n"
            "---\n\n"
            "Activity notes:\n{activities_text}\n\n"
            "Previous draft:\n{draft}\n\n"
            "Reviewer feedback:\n{feedback}\n\n"
            "Please revise the EOD report based on the feedback:",
        ),
    ]
)


def format_few_shot_examples() -> str:
    """Format few-shot examples into a string for the prompt."""
    parts = []
    for i, ex in enumerate(FEW_SHOT_EXAMPLES, 1):
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

### `eod_reporter/agent/nodes.py`

```python
from datetime import date

from langchain_anthropic import ChatAnthropic
from sqlalchemy.orm import Session

from eod_reporter.agent.state import EODState
from eod_reporter.agent.prompts import (
    GENERATE_PROMPT,
    REVIEW_PROMPT,
    REVISE_PROMPT,
    format_few_shot_examples,
    format_activities_for_prompt,
)
from eod_reporter.database import SessionLocal
from eod_reporter.services.activity_service import get_activities_grouped

# Initialize the LLM — model name can be overridden via config
_llm: ChatAnthropic | None = None


def get_llm(model: str = "claude-sonnet-4-6") -> ChatAnthropic:
    global _llm
    if _llm is None:
        _llm = ChatAnthropic(model=model, max_tokens=1024)
    return _llm


# ──────────────────────────────────────────────
# Node: Fetch activities from database
# ──────────────────────────────────────────────

def fetch_activities(state: EODState) -> dict:
    """Pull today's activities from SQLite and populate state."""
    target_date = date.fromisoformat(state["date"])
    db: Session = SessionLocal()
    try:
        grouped = get_activities_grouped(db, target_date)

        # Convert to serializable dicts
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
    """Generate a narrative EOD from the grouped activities."""
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
# Node: Self-review the draft
# ──────────────────────────────────────────────

def self_review(state: EODState) -> dict:
    """Review the draft for quality. Returns approval status and feedback."""
    llm = get_llm()
    chain = REVIEW_PROMPT | llm

    activities_text = format_activities_for_prompt(state["grouped_activities"])
    response = chain.invoke({
        "activities_text": activities_text,
        "draft": state["draft"],
    })

    review_text = response.content.strip()

    # Parse the review response
    approved = "APPROVED: yes" in review_text.lower() or "approved: yes" in review_text
    feedback = ""
    if "FEEDBACK:" in review_text:
        feedback = review_text.split("FEEDBACK:")[-1].strip()

    return {
        "review_feedback": feedback,
        "review_approved": approved,
        "revision_count": state.get("revision_count", 0) + (0 if approved else 1),
    }


# ──────────────────────────────────────────────
# Node: Revise the draft based on feedback
# ──────────────────────────────────────────────

def revise_draft(state: EODState) -> dict:
    """Revise the draft based on review feedback."""
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

### `eod_reporter/agent/graph.py`

```python
from langgraph.graph import StateGraph, END

from eod_reporter.agent.state import EODState
from eod_reporter.agent.nodes import (
    fetch_activities,
    generate_draft,
    self_review,
    revise_draft,
)


def should_revise(state: EODState) -> str:
    """Conditional edge: decide whether to revise or finalize."""
    if state.get("review_approved", False):
        return "finalize"
    if state.get("revision_count", 0) >= 2:
        # Cap revisions at 2 — accept the draft as-is
        return "finalize"
    return "revise"


def finalize(state: EODState) -> dict:
    """Copy the approved draft to final_narrative."""
    return {"final_narrative": state["draft"]}


def build_eod_graph() -> StateGraph:
    """Build and compile the LangGraph EOD generation graph."""
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

    # Conditional: review passes → finalize, fails → revise (with cap)
    graph.add_conditional_edges(
        "self_review",
        should_revise,
        {
            "finalize": "finalize",
            "revise": "revise_draft",
        },
    )
    graph.add_edge("revise_draft", "self_review")  # loop back after revision
    graph.add_edge("finalize", END)

    return graph.compile()


# Pre-compiled graph instance
eod_agent = build_eod_graph()
```

---

## Step 5: API Routers

### `eod_reporter/routers/activities.py`

```python
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from eod_reporter.database import get_db
from eod_reporter.models import ActivityCreate, ActivityResponse, ActivityUpdate, TimePeriod
from eod_reporter.services import activity_service

router = APIRouter(prefix="/activities", tags=["activities"])


# ──────────────────────────────────────────────
# JSON API endpoints
# ──────────────────────────────────────────────

@router.post("/", response_model=ActivityResponse)
def create_activity(payload: ActivityCreate, db: Session = Depends(get_db)):
    """Log a new activity."""
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
def list_activities(
    target_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """List activities for a date (defaults to today)."""
    target = target_date or date.today()
    activities = activity_service.get_activities_by_date(db, target)
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
    """Update an activity."""
    updates = payload.model_dump(exclude_none=True)
    activity = activity_service.update_activity(db, activity_id, **updates)
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
    """Delete an activity."""
    if not activity_service.delete_activity(db, activity_id):
        raise HTTPException(status_code=404, detail="Activity not found")
    return {"ok": True}


# ──────────────────────────────────────────────
# HTMX form endpoint (used by the web dashboard)
# ──────────────────────────────────────────────

@router.post("/log")
def log_from_form(
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    """Log activity from the web form (HTMX POST). Redirects back to dashboard."""
    activity_service.log_activity(db, content=content)
    return RedirectResponse(url="/", status_code=303)
```

### `eod_reporter/routers/reports.py`

```python
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from eod_reporter.database import get_db
from eod_reporter.models import EODReportResponse, EODReportUpdate, ReportStatus
from eod_reporter.services import report_service, activity_service
from eod_reporter.services.teams_poster import TeamsPoster
from eod_reporter.agent.graph import eod_agent

import os

router = APIRouter(prefix="/reports", tags=["reports"])
templates = Jinja2Templates(directory="eod_reporter/templates")


@router.post("/generate")
def generate_report(
    target_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Trigger the LangGraph agent to generate an EOD report."""
    target = target_date or date.today()

    # Check if there are activities
    activities = activity_service.get_activities_by_date(db, target)
    if not activities:
        raise HTTPException(status_code=400, detail="No activities logged for this date")

    # Run the LangGraph agent
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

    # Save to database
    report = report_service.save_report(db, target, narrative)

    return {
        "id": report.id,
        "date": report.date.isoformat(),
        "narrative": report.narrative,
        "status": report.status.value,
    }


@router.get("/preview", response_class=HTMLResponse)
def preview_report(
    request: Request,
    target_date: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Show the preview page for an EOD report."""
    target = target_date or date.today()
    report = report_service.get_report_by_date(db, target)
    return templates.TemplateResponse(
        "preview.html",
        {
            "request": request,
            "report": report,
            "target_date": target,
        },
    )


@router.post("/{report_id}/update")
def update_narrative(
    report_id: int,
    narrative: str = Form(...),
    db: Session = Depends(get_db),
):
    """Update the narrative (from the edit form)."""
    report = report_service.update_report_narrative(db, report_id, narrative)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return RedirectResponse(url=f"/reports/preview?target_date={report.date}", status_code=303)


@router.post("/{report_id}/post-to-teams")
def post_to_teams(
    report_id: int,
    db: Session = Depends(get_db),
):
    """Confirm and post the report to Teams."""
    report = db.query(report_service.EODReport).filter_by(id=report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    webhook_url = os.getenv("TEAMS_WEBHOOK_URL")
    if not webhook_url:
        raise HTTPException(status_code=500, detail="TEAMS_WEBHOOK_URL not configured")

    poster = TeamsPoster(webhook_url)
    try:
        poster.post(report)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to post to Teams: {e}")

    report_service.mark_posted(db, report_id)
    return RedirectResponse(url=f"/reports/preview?target_date={report.date}", status_code=303)


@router.get("/history", response_class=HTMLResponse)
def report_history(request: Request, db: Session = Depends(get_db)):
    """Show past EOD reports."""
    reports = report_service.get_report_history(db)
    return templates.TemplateResponse(
        "history.html",
        {"request": request, "reports": reports},
    )
```

---

## Step 6: Web Templates

### `eod_reporter/templates/base.html`

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

### `eod_reporter/templates/dashboard.html`

```html
{% extends "base.html" %}
{% block title %}Dashboard — EOD Reporter{% endblock %}

{% block content %}
<h1>{{ today.strftime("%B %-d, %Y") }}</h1>

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
                    <form method="post" action="/activities/{{ activity.id }}"
                          hx-delete="/activities/{{ activity.id }}"
                          hx-target="closest .activity-item"
                          hx-swap="outerHTML"
                          hx-confirm="Delete this activity?">
                        <button type="submit" class="btn-delete" title="Delete">✕</button>
                    </form>
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
    <form method="post" action="/reports/generate" id="generate-form">
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

### `eod_reporter/templates/preview.html`

```html
{% extends "base.html" %}
{% block title %}Preview — EOD Reporter{% endblock %}

{% block content %}
<h1>EOD Preview — {{ target_date.strftime("%B %-d, %Y") }}</h1>

{% if report %}
<section class="card">
    <!-- Status Badge -->
    <div class="status-badge status-{{ report.status.value }}">
        {{ report.status.value | upper }}
    </div>

    <!-- Narrative Preview -->
    <div class="preview-box">
        <h3>{{ target_date.strftime("%B %-d, %Y") }}</h3>
        <p>{{ report.narrative }}</p>
    </div>

    <!-- Edit Form -->
    {% if report.status.value != "posted" %}
    <details>
        <summary>Edit narrative</summary>
        <form method="post" action="/reports/{{ report.id }}/update">
            <textarea name="narrative" rows="8">{{ report.narrative }}</textarea>
            <button type="submit">Save Changes</button>
        </form>
    </details>

    <!-- Post to Teams -->
    <form method="post" action="/reports/{{ report.id }}/post-to-teams" class="post-form">
        <button type="submit" class="btn-primary btn-post"
                onclick="return confirm('Post this EOD to Teams?')">
            Post to Teams
        </button>
    </form>
    {% else %}
    <p class="posted-notice">
        Posted to Teams at {{ report.posted_at.strftime("%H:%M on %B %-d, %Y") }}
    </p>
    {% endif %}

    <!-- Regenerate -->
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

### `eod_reporter/templates/history.html`

```html
{% extends "base.html" %}
{% block title %}History — EOD Reporter{% endblock %}

{% block content %}
<h1>Report History</h1>

{% if reports %}
{% for report in reports %}
<section class="card history-card">
    <div class="history-header">
        <h3>{{ report.date.strftime("%B %-d, %Y") }}</h3>
        <span class="status-badge status-{{ report.status.value }}">
            {{ report.status.value }}
        </span>
    </div>
    <p>{{ report.narrative }}</p>
    <div class="history-meta">
        Generated: {{ report.generated_at.strftime("%H:%M") }}
        {% if report.posted_at %}
        · Posted: {{ report.posted_at.strftime("%H:%M") }}
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

---

## Step 7: Static Files

### `eod_reporter/static/style.css`

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

## Step 8: FastAPI App (Main Entry Point)

### `eod_reporter/main.py`

```python
import os
from contextlib import asynccontextmanager
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from eod_reporter.database import init_db, SessionLocal
from eod_reporter.routers import activities, reports
from eod_reporter.services.activity_service import get_activities_grouped, get_activities_by_date
from eod_reporter.services.report_service import save_report
from eod_reporter.agent.graph import eod_agent

load_dotenv()

scheduler = BackgroundScheduler()


def scheduled_eod_generation():
    """Called by APScheduler at the configured time. Generates a draft EOD if activities exist."""
    db = SessionLocal()
    try:
        today = date.today()
        activities_list = get_activities_by_date(db, today)
        if not activities_list:
            print("[Scheduler] No activities logged today. Skipping EOD generation.")
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
        save_report(db, today, narrative)
        print(f"[Scheduler] EOD draft saved. Visit /reports/preview to review and post.")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    # Startup
    init_db()

    # Schedule EOD generation
    schedule_time = os.getenv("EOD_SCHEDULE_TIME", "17:00")
    hour, minute = map(int, schedule_time.split(":"))
    scheduler.add_job(
        scheduled_eod_generation,
        "cron",
        hour=hour,
        minute=minute,
        id="eod_generation",
    )
    scheduler.start()
    print(f"[Scheduler] EOD generation scheduled daily at {schedule_time}")

    yield

    # Shutdown
    scheduler.shutdown()


app = FastAPI(title="EOD Reporter", lifespan=lifespan)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="eod_reporter/static"), name="static")
templates = Jinja2Templates(directory="eod_reporter/templates")

# Include routers
app.include_router(activities.router)
app.include_router(reports.router)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    """Main dashboard: log activities and view today's entries."""
    db = SessionLocal()
    try:
        today = date.today()
        grouped = get_activities_grouped(db, today)
        all_activities = get_activities_by_date(db, today)
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "today": today,
                "grouped_activities": grouped,
                "has_activities": len(all_activities) > 0,
            },
        )
    finally:
        db.close()
```

---

## Step 9: CLI

### `eod_reporter/cli.py`

```python
import os
import webbrowser
from datetime import date

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from eod_reporter.database import init_db, SessionLocal
from eod_reporter.models import TimePeriod
from eod_reporter.services.activity_service import log_activity, get_activities_grouped
from eod_reporter.services.report_service import get_report_by_date, save_report
from eod_reporter.services.teams_poster import TeamsPoster
from eod_reporter.agent.graph import eod_agent

load_dotenv()
init_db()

app = typer.Typer(help="EOD Reporter — Log activities and generate End of Day reports")
console = Console()


@app.command()
def log(
    content: str = typer.Argument(..., help="What you did (e.g., 'Had team huddle')"),
    time: str = typer.Option(
        None, "--time", "-t",
        help="Override time period: morning, afternoon, or evening",
    ),
):
    """Log an activity with the current timestamp."""
    db = SessionLocal()
    try:
        override = TimePeriod(time) if time else None
        activity = log_activity(db, content=content, time_period_override=override)
        period = activity.effective_time_period.value
        console.print(
            f"[green]✓[/green] Logged at {activity.logged_at.strftime('%H:%M')} "
            f"[dim]({period})[/dim]: {content}"
        )
    finally:
        db.close()


@app.command(name="list")
def list_activities(
    target_date: str = typer.Option(
        None, "--date", "-d",
        help="Date to show (YYYY-MM-DD), defaults to today",
    ),
):
    """Show today's logged activities grouped by time period."""
    db = SessionLocal()
    try:
        d = date.fromisoformat(target_date) if target_date else date.today()
        grouped = get_activities_grouped(db, d)

        table = Table(title=f"Activities — {d.strftime('%B %-d, %Y')}")
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
    target_date: str = typer.Option(
        None, "--date", "-d",
        help="Date to compile (YYYY-MM-DD), defaults to today",
    ),
):
    """Generate an EOD report using the LangGraph agent."""
    db = SessionLocal()
    try:
        d = date.fromisoformat(target_date) if target_date else date.today()
        grouped = get_activities_grouped(db, d)

        total = sum(len(v) for v in grouped.values())
        if total == 0:
            console.print("[yellow]No activities logged for this date.[/yellow]")
            raise typer.Exit(1)

        console.print(f"\n[bold blue]Generating EOD for {d.strftime('%B %-d, %Y')}...[/bold blue]")

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
        report = save_report(db, d, narrative)

        console.print(Panel(
            narrative,
            title=f"EOD Report — {d.strftime('%B %-d, %Y')}",
            border_style="green",
        ))
        console.print(f"[dim]Word count: {len(narrative.split())}[/dim]")
        console.print(f"[dim]Report saved as draft (ID: {report.id})[/dim]")
        console.print(
            f"\n[bold]Open [link=http://localhost:8000/reports/preview?target_date={d}]"
            f"http://localhost:8000/reports/preview?target_date={d}[/link] to review and post.[/bold]"
        )
    finally:
        db.close()


@app.command()
def post(
    target_date: str = typer.Option(
        None, "--date", "-d",
        help="Date of report to post (YYYY-MM-DD), defaults to today",
    ),
):
    """Post the latest report to Teams."""
    db = SessionLocal()
    try:
        d = date.fromisoformat(target_date) if target_date else date.today()
        report = get_report_by_date(db, d)

        if not report:
            console.print("[yellow]No report found. Run 'compile' first.[/yellow]")
            raise typer.Exit(1)

        console.print(Panel(report.narrative, title="Report to post", border_style="blue"))

        confirm = typer.confirm("Post this to Teams?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()

        webhook_url = os.getenv("TEAMS_WEBHOOK_URL")
        if not webhook_url:
            console.print("[red]TEAMS_WEBHOOK_URL not set in .env[/red]")
            raise typer.Exit(1)

        poster = TeamsPoster(webhook_url)
        poster.post(report)
        console.print("[bold green]Posted to Teams![/bold green]")
    finally:
        db.close()


@app.command()
def test_webhook():
    """Test the Teams webhook connection."""
    webhook_url = os.getenv("TEAMS_WEBHOOK_URL")
    if not webhook_url:
        console.print("[red]TEAMS_WEBHOOK_URL not set in .env[/red]")
        raise typer.Exit(1)

    poster = TeamsPoster(webhook_url)
    if poster.test_connection():
        console.print("[bold green]Webhook is working! Check your Teams channel.[/bold green]")
    else:
        console.print("[bold red]Webhook test failed. Check the URL in .env.[/bold red]")


if __name__ == "__main__":
    app()
```

---

## Step 10: Running the App

### Start the web server

```bash
cd "c:\Users\Jansen Cruz\Desktop\Jansen\internity"

# Run with uv
uv run uvicorn eod_reporter.main:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

### Use the CLI

Open another terminal:

```bash
cd "c:\Users\Jansen Cruz\Desktop\Jansen\internity"

# Log activities throughout the day
uv run python -m eod_reporter.cli log "Had weekly team huddle"
uv run python -m eod_reporter.cli log "Tested workflow agent responses"
uv run python -m eod_reporter.cli log "Daily check-in with David and Matt"
uv run python -m eod_reporter.cli log "Worked on PDF conversion service" --time afternoon

# View today's activities
uv run python -m eod_reporter.cli list

# Generate EOD report
uv run python -m eod_reporter.cli compile

# Post to Teams (from CLI)
uv run python -m eod_reporter.cli post

# Test webhook connection
uv run python -m eod_reporter.cli test-webhook
```

### Alternative: Register the CLI as a script

Add this to your `pyproject.toml` so you can run `eod` directly:

```toml
[project.scripts]
eod = "eod_reporter.cli:app"
```

Then you can use:

```bash
uv run eod log "Had team huddle"
uv run eod list
uv run eod compile
uv run eod post
```

---

## Quick Reference

| Action | CLI Command | Web |
|---|---|---|
| Log activity | `uv run eod log "text"` | Dashboard → type and submit |
| Log with time override | `uv run eod log "text" --time morning` | Dashboard → edit dropdown |
| View activities | `uv run eod list` | Dashboard |
| Generate EOD | `uv run eod compile` | Dashboard → "Generate Report" |
| Preview EOD | Open browser link after compile | `/reports/preview` |
| Edit EOD | Web only | Preview → "Edit narrative" |
| Post to Teams | `uv run eod post` | Preview → "Post to Teams" |
| View history | Web only | `/reports/history` |
| Test webhook | `uv run eod test-webhook` | — |

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `ANTHROPIC_API_KEY not set` | Make sure `.env` exists and has your key |
| `TEAMS_WEBHOOK_URL not set` | Add your webhook URL to `.env` |
| Webhook returns 400/403 | Recreate the webhook in Teams Workflows app |
| `ModuleNotFoundError` | Run `uv sync` to install dependencies |
| Database errors | Delete `eod_reporter.db` and restart (tables will be recreated) |
| LLM returns bullet points | The self-review node should catch this; if persistent, add more few-shot examples to `prompts.py` |
| `strftime %-d` errors on Windows | Replace `%-d` with `%#d` in all `.strftime()` calls (Windows uses `%#d` instead of `%-d` for day without leading zero) |

---

## What's Next (Optional Enhancements)

- **Desktop notifications** when the scheduler generates a draft (use `plyer` or `win10toast`)
- **Slack integration** as an alternative to Teams
- **Docker deployment** for always-on access
- **Add more few-shot examples** over time from your best EODs to improve generation quality
- **Weekly summary** agent that compiles all EODs from the week into a weekly report
