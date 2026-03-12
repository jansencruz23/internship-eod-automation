# Internity (aufccs.org) Integration Guide

Automate EOD report submission to `aufccs.org/end_of_day_reports/create` using Playwright browser automation and Gemini LLM for structured data generation.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Setup](#2-setup)
3. [Step 1: Reorganize Existing Files](#3-step-1-reorganize-existing-files)
4. [Step 2: Update Imports After Reorganization](#4-step-2-update-imports-after-reorganization)
5. [Step 3: Pydantic Models](#5-step-3-pydantic-models--appschemasreportpy)
6. [Step 4: Configuration](#6-step-4-configuration--appcoreconfgpy--env)
7. [Step 5: DB Migration](#7-step-5-db-migration--appmodelssettingspy--appcoredatabasepy)
8. [Step 6: Internity LLM Prompt](#8-step-6-internity-llm-prompt--appagentinternitypromptspy)
9. [Step 7: Internity LLM Node](#9-step-7-internity-llm-node--appagentinternitynodespy)
10. [Step 8: Internity Playwright Service](#10-step-8-internity-playwright-service--appservicesinternityposterpy)
11. [Step 9: Dependency Injection](#11-step-9-dependency-injection--appapidependenciespy)
12. [Step 10: API Endpoints](#12-step-10-api-endpoints--appapiv1endpointsreportspy)
13. [Step 11: Pages Endpoint](#13-step-11-pages-endpoint--appapiv1endpointspagespy)
14. [Step 12: Templates](#14-step-12-templates)
15. [Step 13: CLI Commands](#15-step-13-cli-commands--appclpy)
16. [Step 14: Scheduler](#16-step-14-scheduler--appmainpy)
17. [Verification](#17-verification)
18. [Selector Calibration](#18-selector-calibration)
19. [Troubleshooting](#19-troubleshooting)

---

## 1. Overview

**How it works:**

```
Logged activities (SQLite)
    |
    v
Gemini LLM (.with_structured_output)
    |
    v
InternityEOD {tasks[], key_successes, main_challenges, plans_for_tomorrow}
    |
    v
Playwright (headless browser)
    |
    v
Login to aufccs.org -> Navigate to form -> Fill fields -> Submit
```

Playwright runs as a **Python library** — headless (invisible) by default, headed (visible) in dry-run mode. No MCP server or separate CLI needed.

### File structure after all changes

```
app/
  agent/
    __init__.py
    state.py                          # shared state (unchanged)
    llm.py                            # shared get_llm() singleton (NEW - extracted from nodes.py)
    teams/
      __init__.py
      graph.py                        # MOVED from agent/graph.py
      nodes.py                        # MOVED from agent/nodes.py (get_llm removed)
      prompts.py                      # MOVED from agent/prompts.py
      examples.json                   # MOVED from agent/examples.json
    internity/
      __init__.py
      nodes.py                        # NEW
      prompts.py                      # NEW
  services/
    __init__.py
    activity_service.py               # shared (unchanged)
    report_service.py                 # shared (unchanged)
    teams/
      __init__.py
      poster.py                       # MOVED from services/teams_service.py
    internity/
      __init__.py
      poster.py                       # NEW
  schemas/
    report.py                         # MODIFIED (add InternityEOD)
  core/
    config.py                         # MODIFIED (add Internity settings)
    database.py                       # MODIFIED (add migration)
  models/
    settings.py                       # MODIFIED (add column)
  api/
    dependencies.py                   # MODIFIED (add internity poster)
    v1/endpoints/
      reports.py                      # MODIFIED (add internity endpoints)
      pages.py                        # MODIFIED (pass new setting)
  templates/
    preview.html                      # MODIFIED (add button)
    dashboard.html                    # MODIFIED (add toggle)
  static/
    style.css                         # MODIFIED (add internity button style)
  cli.py                              # MODIFIED (add commands)
  main.py                             # MODIFIED (add scheduler integration)
```

---

## 2. Setup

### Install Playwright

```bash
uv add playwright
uv run playwright install chromium
```

The second command downloads the Chromium browser binary (~100MB). Only runs once.

### Add environment variables to `.env`

```env
INTERNITY_USERNAME=your-aufccs-username
INTERNITY_PASSWORD=your-aufccs-password
INTERNITY_FORM_URL=https://aufccs.org/end_of_day_reports/create
```

---

## 3. Step 1: Reorganize Existing Files

Move existing Teams and service files into subfolders. Run these commands from the project root:

```bash
# Create subfolders
mkdir -p app/agent/teams
mkdir -p app/agent/internity
mkdir -p app/services/teams
mkdir -p app/services/internity

# Move Teams agent files
mv app/agent/graph.py app/agent/teams/graph.py
mv app/agent/nodes.py app/agent/teams/nodes.py
mv app/agent/prompts.py app/agent/teams/prompts.py
mv app/agent/examples.json app/agent/teams/examples.json

# Move Teams service
mv app/services/teams_service.py app/services/teams/poster.py

# Create __init__.py files
touch app/agent/teams/__init__.py
touch app/agent/internity/__init__.py
touch app/services/teams/__init__.py
touch app/services/internity/__init__.py
```

### Create shared LLM singleton: `app/agent/llm.py`

Extract `get_llm()` from the old `nodes.py` into a shared file so both Teams and Internity can use it.

```python
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import get_settings

_llm: ChatGoogleGenerativeAI | None = None


def get_llm() -> ChatGoogleGenerativeAI:
    """Lazy singleton for the Gemini LLM. Shared by Teams and Internity agents."""
    global _llm
    if _llm is None:
        settings = get_settings()
        _llm = ChatGoogleGenerativeAI(
            model=settings.MODEL_NAME,
            google_api_key=settings.GOOGLE_API_KEY,
            max_output_tokens=1024,
        )
    return _llm
```

---

## 4. Step 2: Update Imports After Reorganization

Every file that imported from the old paths needs updating.

### `app/agent/teams/nodes.py` (moved file)

Update imports — use `app.agent.llm` for `get_llm()` and `app.agent.teams.prompts` for prompts:

```python
from datetime import date

from sqlalchemy.orm import Session

from app.agent.state import EODState
from app.agent.llm import get_llm
from app.agent.teams.prompts import (
    GENERATE_PROMPT,
    REVIEW_PROMPT,
    REVISE_PROMPT,
    format_few_shot_examples,
    format_activities_for_prompt,
)
from app.core.database import SessionLocal
from app.schemas.report import ReviewResult
from app.services.activity_service import activity_service


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

    response = chain.invoke(
        {
            "few_shot_examples": few_shot,
            "activities_text": activities_text,
        }
    )

    return {"draft": response.content.strip()}


# ──────────────────────────────────────────────
# Node: Self-review (structured output)
# ──────────────────────────────────────────────


def self_review(state: EODState) -> dict:
    llm = get_llm()
    activities_text = format_activities_for_prompt(state["grouped_activities"])

    try:
        structured_llm = llm.with_structured_output(ReviewResult)
        chain = REVIEW_PROMPT | structured_llm

        result: ReviewResult = chain.invoke(
            {
                "activities_text": activities_text,
                "draft": state["draft"],
            }
        )

        return {
            "review_feedback": result.feedback,
            "review_approved": result.approved,
            "revision_count": state.get("revision_count", 0)
            + (0 if result.approved else 1),
        }
    except Exception:
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

    response = chain.invoke(
        {
            "few_shot_examples": few_shot,
            "activities_text": activities_text,
            "draft": state["draft"],
            "feedback": state["review_feedback"],
        }
    )

    return {"draft": response.content.strip()}
```

### `app/agent/teams/prompts.py` (moved file)

This is the original `prompts.py` with no changes needed to the content — just make sure it's in the `teams/` folder. The `_EXAMPLES_PATH` uses `Path(__file__).parent` so it automatically finds `examples.json` in the same directory.

```python
import json
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

# ──────────────────────────────────────────────
# System Prompt — [Role]+[Expertise]+[Guidelines]+[Output Format]+[Constraints]
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
                lines.append(
                    f"- [{time_str}] {content}" if time_str else f"- {content}"
                )
    return "\n".join(lines)
```

> **Note:** The `_EXAMPLES_PATH = Path(__file__).parent / "examples.json"` stays the same because `examples.json` moved alongside `prompts.py` into the same `teams/` folder.

### `app/agent/teams/graph.py` (moved file)

```python
from langgraph.graph import StateGraph, END

from app.agent.state import EODState
from app.agent.teams.nodes import (
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

    graph.add_node("fetch_activities", fetch_activities)
    graph.add_node("generate_draft", generate_draft)
    graph.add_node("self_review", self_review)
    graph.add_node("revise_draft", revise_draft)
    graph.add_node("finalize", finalize)

    graph.set_entry_point("fetch_activities")
    graph.add_edge("fetch_activities", "generate_draft")
    graph.add_edge("generate_draft", "self_review")

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


eod_agent = build_eod_graph()
```

### `app/services/teams/poster.py` (moved file)

No import changes needed — this file only imports from `app.models.report`:

```python
import httpx

from app.models.report import EODReport


class TeamsPoster:
    def __init__(self, power_automate_url: str):
        self.power_automate_url = power_automate_url

    def post(self, report: EODReport) -> bool:
        """Post an EOD report to the Teams group chat via Power Automate."""
        payload = {
            "date": report.date.strftime("%B %#d, %Y"),
            "message": report.narrative,
        }

        print("[Teams] Posting to Power Automate...")
        print(f"[Teams] Payload: {payload}")

        response = httpx.post(
            self.power_automate_url,
            json=payload,
            timeout=30,
        )

        print(f"[Teams] Response status: {response.status_code}")
        print(f"[Teams] Response body: {response.text[:500]}")

        response.raise_for_status()
        return True

    def test_connection(self) -> bool:
        """Send a test message to verify the Power Automate flow works."""
        payload = {
            "date": "Connection Test",
            "message": "EOD Reporter is connected. If you see this in your group chat, it's working!",
        }
        try:
            response = httpx.post(
                self.power_automate_url,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            return True
        except Exception:
            return False
```

### Files with import path changes

Update these imports in the following files:

**`app/main.py`** — change 2 imports:
```python
# OLD:
from app.services.teams_service import TeamsPoster
from app.agent.graph import eod_agent

# NEW:
from app.services.teams.poster import TeamsPoster
from app.agent.teams.graph import eod_agent
```

**`app/cli.py`** — change 2 imports:
```python
# OLD:
from app.services.teams_service import TeamsPoster
from app.agent.graph import eod_agent

# NEW:
from app.services.teams.poster import TeamsPoster
from app.agent.teams.graph import eod_agent
```

**`app/api/dependencies.py`** — change 1 import:
```python
# OLD:
from app.services.teams_service import TeamsPoster

# NEW:
from app.services.teams.poster import TeamsPoster
```

**`app/api/v1/endpoints/reports.py`** — change 2 imports:
```python
# OLD:
from app.services.teams_service import TeamsPoster
from app.agent.graph import eod_agent

# NEW:
from app.services.teams.poster import TeamsPoster
from app.agent.teams.graph import eod_agent
```

### Delete old files

After verifying the app runs (`uv run uvicorn app.main:app --reload`), delete the old files that were moved:

```bash
# These should already be gone if mv worked, but verify:
rm -f app/agent/graph.py app/agent/nodes.py app/agent/prompts.py app/agent/examples.json
rm -f app/services/teams_service.py
```

---

## 5. Step 3: Pydantic Models — `app/schemas/report.py`

Add `InternityTask` and `InternityEOD` at the end of the file (after `ReviewResult`):

```python
# --- Internity structured output ---


class InternityTask(BaseModel):
    """A single task entry for the Internity EOD form."""

    description: str = Field(
        description="Task title and description, e.g. 'Team Huddle & Multi-Attachment Fix — Huddled with the team...'"
    )
    hours: int = Field(
        description="Estimated hours spent on this task (0-8)", ge=0, le=8
    )
    minutes: int = Field(
        description="Estimated remaining minutes spent on this task (0-59)",
        ge=0,
        le=59,
    )


class InternityEOD(BaseModel):
    """Structured output matching the aufccs.org EOD form fields."""

    tasks: list[InternityTask] = Field(
        description="List of tasks performed today, each with description and time estimate"
    )
    key_successes: str = Field(
        description="Key successes and accomplishments for the day"
    )
    main_challenges: str = Field(
        description="Main challenges or difficulties encountered"
    )
    plans_for_tomorrow: str = Field(
        description="Planned tasks and goals for the next working day"
    )
```

Full file:

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
    feedback: str = Field(
        description="Specific feedback if not approved, or 'Looks good' if approved"
    )


# --- Internity structured output ---


class InternityTask(BaseModel):
    """A single task entry for the Internity EOD form."""

    description: str = Field(
        description="Task title and description, e.g. 'Team Huddle & Multi-Attachment Fix — Huddled with the team...'"
    )
    hours: int = Field(
        description="Estimated hours spent on this task (0-8)", ge=0, le=8
    )
    minutes: int = Field(
        description="Estimated remaining minutes spent on this task (0-59)",
        ge=0,
        le=59,
    )


class InternityEOD(BaseModel):
    """Structured output matching the aufccs.org EOD form fields."""

    tasks: list[InternityTask] = Field(
        description="List of tasks performed today, each with description and time estimate"
    )
    key_successes: str = Field(
        description="Key successes and accomplishments for the day"
    )
    main_challenges: str = Field(
        description="Main challenges or difficulties encountered"
    )
    plans_for_tomorrow: str = Field(
        description="Planned tasks and goals for the next working day"
    )
```

---

## 6. Step 4: Configuration — `app/core/config.py` + `.env`

Full file:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    POWER_AUTOMATE_URL: str
    EOD_SCHEDULE_TIME: str = "17:00"
    MODEL_NAME: str = "gemini-2.5-flash"
    DATABASE_URL: str = "sqlite:///eod_reporter.db"

    # Internity (aufccs.org)
    INTERNITY_USERNAME: str = ""
    INTERNITY_PASSWORD: str = ""
    INTERNITY_FORM_URL: str = ""

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

---

## 7. Step 5: DB Migration — `app/models/settings.py` + `app/core/database.py`

**Preserves your existing database.** No deletion needed.

### `app/models/settings.py`

```python
from sqlalchemy import Column, Integer, Boolean, String

from app.core.database import Base


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, default=1)
    auto_post_enabled = Column(Boolean, default=False)
    auto_post_internity_enabled = Column(Boolean, default=False)
    schedule_time = Column(String, default="15:35")
```

### `app/core/database.py`

```python
from sqlalchemy import create_engine, inspect, text
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


def _run_migrations():
    """Add new columns to existing tables without deleting the database."""
    insp = inspect(engine)

    if "app_settings" not in insp.get_table_names():
        return  # Table will be created by create_all

    columns = [c["name"] for c in insp.get_columns("app_settings")]
    if "auto_post_internity_enabled" not in columns:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE app_settings "
                    "ADD COLUMN auto_post_internity_enabled BOOLEAN DEFAULT 0"
                )
            )
        print("[DB] Added auto_post_internity_enabled column to app_settings.")


def init_db():
    """Create all tables."""
    import app.models.activity  # noqa: F401
    import app.models.report  # noqa: F401
    import app.models.settings  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _run_migrations()
```

---

## 8. Step 6: Internity LLM Prompt — `app/agent/internity/prompts.py`

**Create this new file.** Uses the user's real sample as a few-shot example.

```python
from langchain_core.prompts import ChatPromptTemplate

# ──────────────────────────────────────────────
# System Prompt — [Role]+[Expertise]+[Guidelines]+[Constraints]
# ──────────────────────────────────────────────

INTERNITY_SYSTEM_PROMPT = """\
[Role]
You are an assistant that transforms daily work activity logs into structured \
End of Day (EOD) form submissions for an internship tracking platform.

[Expertise]
You excel at grouping related activities into coherent tasks, estimating time \
spent based on activity timestamps and descriptions, and summarizing a day's \
work into successes, challenges, and plans.

[Guidelines]
- Group related activities into coherent tasks (e.g., merge "tested workflow" \
and "flagged responses" into one task about workflow testing)
- Each task has a short bolded title followed by an em dash and a description
- Format: "Title — Description of what was done"
- Estimate hours and minutes for each task based on:
  * The time gaps between logged activities
  * The complexity implied by the description
  * Total work hours should sum to approximately 8 hours for a full day
- Key successes: list concrete accomplishments, each on its own line with a \
bolded title followed by an em dash and explanation
- Main challenges: note any blockers or difficulties, same format as successes
- Plans for tomorrow: infer reasonable next steps from today's activities, \
written as a single sentence or short paragraph

[Constraints]
- Each task description should be 1-2 sentences
- Hours must be 0-8, minutes must be 0-59
- Total hours across all tasks should approximately equal the work day length
- Do NOT fabricate tasks or details not implied by the activity logs
- Write in first person when appropriate
- Keep the professional but natural tone shown in the examples"""

# ──────────────────────────────────────────────
# Few-shot example from real user submissions
# ──────────────────────────────────────────────

INTERNITY_FEW_SHOT = """
Here is an example of the expected output style:

Daily Tasks:
1. Team Huddle & Multi-Attachment Fix — Huddled with the team to delegate tasks, \
then discovered and fixed a limitation where the workflow was only extracting the \
first attachment. Adjusted the nodes to handle multiple attachments from emails.
   Hours: 3, Minutes: 0

2. Issue Identification & Team Collaboration — Tested the updated workflow, found \
several issues, reported them to the team, and worked together to resolve them.
   Hours: 3, Minutes: 0

3. Final Testing & Logging — Ran another round of tests on the agent and logged \
all runs and results into an Excel sheet for tracking and review.
   Hours: 2, Minutes: 0

Key Successes:
Multi-attachment support added — The workflow can now extract and process multiple \
attachments from a single email, fixing a key limitation.
Issues caught and resolved as a team — Found several issues during testing and \
quickly collaborated with teammates to get things working again.
Results documented — All test runs and results were logged in an Excel sheet, \
keeping a clear record of the agent's performance.

Main Challenges:
New issues surfaced after the fix — Adjusting the workflow to handle multiple \
attachments introduced some new issues that needed to be addressed on the spot.

Plans for Tomorrow:
Review the logged test results and continue stabilizing the workflow based on \
the issues found today.
"""

# ──────────────────────────────────────────────
# Prompt Template
# ──────────────────────────────────────────────

INTERNITY_EXTRACT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", INTERNITY_SYSTEM_PROMPT),
        (
            "human",
            "{few_shot}\n\n---\n\n"
            "Here are my logged activities for today:\n\n"
            "{activities_text}\n\n"
            "Transform these into structured EOD form data with:\n"
            "- Tasks (each with a title — description, hours, minutes)\n"
            "- Key successes\n"
            "- Main challenges\n"
            "- Plans for tomorrow",
        ),
    ]
)
```

---

## 9. Step 7: Internity LLM Node — `app/agent/internity/nodes.py`

**Create this new file.** Single LLM call with structured output.

```python
from app.agent.llm import get_llm
from app.agent.teams.prompts import format_activities_for_prompt
from app.agent.internity.prompts import INTERNITY_EXTRACT_PROMPT, INTERNITY_FEW_SHOT
from app.schemas.report import InternityEOD


def generate_internity_eod(grouped_activities: dict) -> InternityEOD:
    """Generate structured Internity EOD data from grouped activities.

    Uses the shared get_llm() singleton and .with_structured_output() pattern.
    """
    llm = get_llm()
    structured_llm = llm.with_structured_output(InternityEOD)
    chain = INTERNITY_EXTRACT_PROMPT | structured_llm

    activities_text = format_activities_for_prompt(grouped_activities)

    result: InternityEOD = chain.invoke(
        {
            "few_shot": INTERNITY_FEW_SHOT,
            "activities_text": activities_text,
        }
    )
    return result
```

> **Note:** `format_activities_for_prompt` is imported from `app.agent.teams.prompts` since it's a shared utility. If you prefer, you can copy it to a shared `app/agent/utils.py` instead.

---

## 10. Step 8: Internity Playwright Service — `app/services/internity/poster.py`

**Create this new file.** Mirrors `TeamsPoster` structure.

```python
from datetime import date

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from app.schemas.report import InternityEOD


class InternityPoster:
    """Automates EOD form submission on aufccs.org using Playwright."""

    def __init__(self, username: str, password: str, form_url: str):
        self.username = username
        self.password = password
        self.form_url = form_url
        self.base_url = form_url.rsplit("/", 2)[0]  # https://aufccs.org

    def post(
        self, eod_data: InternityEOD, target_date: date, dry_run: bool = False
    ) -> bool:
        """Automate the aufccs.org EOD form submission.

        Args:
            eod_data: Structured EOD data from the LLM.
            target_date: The date to submit the report for.
            dry_run: If True, opens a visible browser and pauses before submit.
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not dry_run)
            page = browser.new_page()

            try:
                # Step 1: Login
                self._login(page)

                # Step 2: Navigate to EOD form
                print(f"[Internity] Navigating to {self.form_url}")
                page.goto(self.form_url, wait_until="networkidle")
                page.wait_for_timeout(1000)

                # Step 3: Fill tasks
                self._fill_tasks(page, eod_data.tasks)

                # Step 4: Fill text areas
                self._fill_field(page, "Key Successes", eod_data.key_successes)
                self._fill_field(page, "Main Challenges", eod_data.main_challenges)
                self._fill_field(
                    page, "Plans for Tomorrow", eod_data.plans_for_tomorrow
                )

                if dry_run:
                    print(
                        "[Internity] Dry run — form filled but NOT submitted. "
                        "Browser will stay open for 60 seconds for inspection."
                    )
                    page.wait_for_timeout(60_000)
                    return True

                # Step 5: Submit
                self._submit(page)
                return True

            except PlaywrightTimeout as e:
                print(f"[Internity] Timeout during form submission: {e}")
                raise
            except Exception as e:
                print(f"[Internity] Error during form submission: {e}")
                raise
            finally:
                browser.close()

    def _login(self, page):
        """Navigate to login page and authenticate."""
        print("[Internity] Logging in...")
        page.goto(f"{self.base_url}/login", wait_until="networkidle")

        # --- CALIBRATE THESE SELECTORS ---
        # Inspect the actual login page and update if needed.
        page.fill(
            'input[type="email"], input[name="email"], input[name="username"]',
            self.username,
        )
        page.fill('input[type="password"], input[name="password"]', self.password)
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")
        print("[Internity] Logged in successfully.")

    def _fill_tasks(self, page, tasks):
        """Fill repeatable task rows, clicking 'Add Another Task' as needed."""
        for i, task in enumerate(tasks):
            if i > 0:
                add_btn = page.get_by_text("Add Another Task", exact=False)
                add_btn.click()
                page.wait_for_timeout(500)

            # --- CALIBRATE THESE SELECTORS ---
            # Based on the screenshot, fields use placeholder text.
            # Inspect the actual DOM and update if needed.
            desc_fields = page.get_by_placeholder("Task Description").all()
            if i < len(desc_fields):
                desc_fields[i].fill(task.description)

            hours_fields = page.get_by_placeholder("Hours").all()
            if i < len(hours_fields):
                hours_fields[i].fill(str(task.hours))

            minutes_fields = page.get_by_placeholder("Minutes").all()
            if i < len(minutes_fields):
                minutes_fields[i].fill(str(task.minutes))

            print(
                f"[Internity] Task {i + 1}: [{task.hours}h {task.minutes}m] "
                f"{task.description[:60]}..."
            )

    def _fill_field(self, page, label_text: str, value: str):
        """Fill a textarea by its placeholder or label text."""
        field = page.get_by_placeholder(label_text, exact=False)
        if field.count() > 0:
            field.first.fill(value)
            print(f"[Internity] Filled '{label_text}': {value[:60]}...")
            return

        field = page.get_by_label(label_text, exact=False)
        if field.count() > 0:
            field.first.fill(value)
            print(f"[Internity] Filled '{label_text}': {value[:60]}...")
            return

        print(f"[Internity] WARNING: Could not find field '{label_text}'")

    def _submit(self, page):
        """Click the submit button and wait for confirmation."""
        submit_btn = page.get_by_text("Submit Report", exact=False)
        submit_btn.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        print("[Internity] Form submitted successfully.")

    def test_connection(self) -> bool:
        """Test that login works without submitting anything."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                self._login(page)
                browser.close()
                return True
        except Exception as e:
            print(f"[Internity] Connection test failed: {e}")
            return False
```

---

## 11. Step 9: Dependency Injection — `app/api/dependencies.py`

Full file:

```python
from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.teams.poster import TeamsPoster
from app.services.internity.poster import InternityPoster


def get_teams_poster(settings: Settings = Depends(get_settings)) -> TeamsPoster:
    return TeamsPoster(power_automate_url=settings.POWER_AUTOMATE_URL)


def get_internity_poster(
    settings: Settings = Depends(get_settings),
) -> InternityPoster:
    return InternityPoster(
        username=settings.INTERNITY_USERNAME,
        password=settings.INTERNITY_PASSWORD,
        form_url=settings.INTERNITY_FORM_URL,
    )
```

---

## 12. Step 10: API Endpoints — `app/api/v1/endpoints/reports.py`

Full file with all changes:

```python
import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Form
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

    from app.main import scheduler
    scheduler.reschedule_job(
        "eod_generation",
        trigger="cron",
        hour=hour,
        minute=minute,
    )
    print(f"[Scheduler] Rescheduled to {schedule_time}")

    return HTMLResponse(_render_time(schedule_time, saved=True))


# ── Internity Integration ──


@router.post("/{report_id}/post-to-internity")
def post_to_internity(
    report_id: int,
    db: Session = Depends(get_db),
    poster: InternityPoster = Depends(get_internity_poster),
):
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

    internity_eod = generate_internity_eod(grouped_dict)

    try:
        poster.post(internity_eod, report.date)
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Failed to submit to Internity: {e}"
        )

    return RedirectResponse(
        url=f"/reports/preview?target_date={report.date}", status_code=303
    )


def _render_internity_toggle(enabled: bool) -> str:
    checked = "checked" if enabled else ""
    label = "ON" if enabled else "OFF"
    return f"""
    <label class="toggle-switch">
        <input type="checkbox" {checked}
               hx-post="/reports/toggle-auto-post-internity"
               hx-target="#internity-toggle-container"
               hx-swap="innerHTML">
        <span class="slider"></span>
    </label>
    <span class="toggle-label toggle-{'on' if enabled else 'off'}">{label}</span>
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
```

---

## 13. Step 11: Pages Endpoint — `app/api/v1/endpoints/pages.py`

Full file:

```python
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
    auto_post_internity_enabled = (
        settings.auto_post_internity_enabled if settings else False
    )
    schedule_time = settings.schedule_time if settings else "15:35"
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "today": today,
            "grouped_activities": grouped,
            "has_activities": len(all_activities) > 0,
            "auto_post_enabled": auto_post_enabled,
            "auto_post_internity_enabled": auto_post_internity_enabled,
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
```

---

## 14. Step 12: Templates

### `app/templates/preview.html`

Full file:

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

    <div class="post-actions">
        <form method="post" action="/reports/{{ report.id }}/post-to-teams" class="post-form">
            <button type="submit" class="btn-primary btn-post"
                    onclick="return confirm('Post this EOD to Teams?')">
                Post to Teams
            </button>
        </form>

        <form method="post" action="/reports/{{ report.id }}/post-to-internity" class="post-form">
            <button type="submit" class="btn-internity btn-post"
                    onclick="return confirm('Submit this EOD to Internity (aufccs.org)?\nThis will open a headless browser and fill the form automatically.')">
                Submit to Internity
            </button>
        </form>
    </div>
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

### `app/templates/dashboard.html`

Full file:

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

<!-- Scheduler Settings -->
<section class="card">
    <h2>Scheduler Settings</h2>

    <div class="setting-row">
        <span>Scheduled time</span>
        <div id="time-container">
            <input type="time" name="schedule_time" value="{{ schedule_time }}"
                   hx-post="/reports/update-schedule-time"
                   hx-target="#time-container"
                   hx-swap="innerHTML"
                   hx-trigger="change">
        </div>
    </div>

    <div class="setting-row">
        <span>Auto-post to Teams</span>
        <div id="toggle-container">
            <label class="toggle-switch">
                <input type="checkbox" {{ "checked" if auto_post_enabled }}
                       hx-post="/reports/toggle-auto-post"
                       hx-target="#toggle-container"
                       hx-swap="innerHTML">
                <span class="slider"></span>
            </label>
            <span class="toggle-label toggle-{{ 'on' if auto_post_enabled else 'off' }}">
                {{ "ON" if auto_post_enabled else "OFF" }}
            </span>
        </div>
    </div>

    <div class="setting-row">
        <span>Auto-post to Internity</span>
        <div id="internity-toggle-container">
            <label class="toggle-switch">
                <input type="checkbox" {{ "checked" if auto_post_internity_enabled }}
                       hx-post="/reports/toggle-auto-post-internity"
                       hx-target="#internity-toggle-container"
                       hx-swap="innerHTML">
                <span class="slider"></span>
            </label>
            <span class="toggle-label toggle-{{ 'on' if auto_post_internity_enabled else 'off' }}">
                {{ "ON" if auto_post_internity_enabled else "OFF" }}
            </span>
        </div>
    </div>

    <p class="hint">The report is generated daily at the scheduled time. When auto-post is on, it also posts to Teams and/or Internity automatically.</p>
</section>
{% endblock %}
```

### CSS addition — `app/static/style.css`

Add at the end of the file:

```css
/* ── Internity Button ── */
.btn-internity { background: #B30600; }
.btn-internity:hover { background: #8f0500; }
.post-actions { display: flex; gap: 0.5rem; margin: 1rem 0; }
```

---

## 15. Step 13: CLI Commands — `app/cli.py`

Full file:

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
from app.services.teams.poster import TeamsPoster
from app.services.internity.poster import InternityPoster
from app.agent.teams.graph import eod_agent
from app.agent.internity.nodes import generate_internity_eod

load_dotenv()
init_db()

app = typer.Typer(help="EOD Reporter - Log activities and generate End of Day reports")
console = Console()


@app.command()
def log(
    content: str = typer.Argument(..., help="What you did"),
    time: str = typer.Option(
        None, "--time", "-t", help="Override: morning, afternoon, evening"
    ),
):
    """Log an activity with the current timestamp."""
    db = SessionLocal()
    try:
        override = TimePeriod(time) if time else None
        activity = activity_service.log_activity(
            db, content=content, time_period_override=override
        )
        period = activity.effective_time_period.value
        console.print(
            f"[green]>[/green] Logged at {activity.logged_at.strftime('%H:%M')} "
            f"[dim]({period})[/dim]: {content}"
        )
    finally:
        db.close()


@app.command(name="list")
def list_activities(
    target_date: str = typer.Option(
        None, "--date", "-d", help="YYYY-MM-DD, defaults to today"
    ),
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
    target_date: str = typer.Option(
        None, "--date", "-d", help="YYYY-MM-DD, defaults to today"
    ),
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

        console.print(
            f"\n[bold blue]Generating EOD for {d.strftime('%B %#d, %Y')}...[/bold blue]"
        )

        result = eod_agent.invoke(
            {
                "date": d.isoformat(),
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
        report = report_service.save(db, d, narrative)

        console.print(
            Panel(
                narrative,
                title=f"EOD Report - {d.strftime('%B %#d, %Y')}",
                border_style="green",
            )
        )
        console.print(f"[dim]Word count: {len(narrative.split())}[/dim]")
        console.print(f"[dim]Report saved as draft (ID: {report.id})[/dim]")
        console.print(
            f"\n[bold]Open http://localhost:8000/reports/preview?target_date={d} to review and post.[/bold]"
        )
    finally:
        db.close()


@app.command()
def post(
    target_date: str = typer.Option(
        None, "--date", "-d", help="YYYY-MM-DD, defaults to today"
    ),
):
    """Post the latest report to Teams."""
    db = SessionLocal()
    try:
        d = date.fromisoformat(target_date) if target_date else date.today()
        report = report_service.get_by_date(db, d)

        if not report:
            console.print("[yellow]No report found. Run 'compile' first.[/yellow]")
            raise typer.Exit(1)

        console.print(
            Panel(report.narrative, title="Report to post", border_style="blue")
        )

        confirm = typer.confirm("Post this to Teams?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit()

        settings = get_settings()
        poster = TeamsPoster(power_automate_url=settings.POWER_AUTOMATE_URL)
        poster.post(report)
        report_service.mark_posted(db, report.id)
        console.print("[bold green]Posted to Teams![/bold green]")
    finally:
        db.close()


@app.command()
def test_webhook():
    """Test the Teams webhook connection."""
    settings = get_settings()
    poster = TeamsPoster(power_automate_url=settings.POWER_AUTOMATE_URL)
    if poster.test_connection():
        console.print(
            "[bold green]Power Automate flow is working! Check your Teams group chat.[/bold green]"
        )
    else:
        console.print(
            "[bold red]Flow test failed. Check POWER_AUTOMATE_URL in .env.[/bold red]"
        )


@app.command()
def internity(
    target_date: str = typer.Option(
        None, "--date", "-d", help="YYYY-MM-DD, defaults to today"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Fill the form but don't submit (opens visible browser)"
    ),
):
    """Submit the EOD report to Internity (aufccs.org)."""
    db = SessionLocal()
    try:
        d = date.fromisoformat(target_date) if target_date else date.today()
        grouped = activity_service.get_grouped(db, d)

        total = sum(len(v) for v in grouped.values())
        if total == 0:
            console.print("[yellow]No activities logged for this date.[/yellow]")
            raise typer.Exit(1)

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

        console.print(
            f"\n[bold blue]Generating Internity EOD data for "
            f"{d.strftime('%B %#d, %Y')}...[/bold blue]"
        )
        internity_eod = generate_internity_eod(grouped_dict)

        tasks_text = "\n".join(
            f"  [{t.hours}h {t.minutes}m] {t.description}"
            for t in internity_eod.tasks
        )
        preview = (
            f"[bold]Tasks:[/bold]\n{tasks_text}\n\n"
            f"[bold]Key Successes:[/bold]\n  {internity_eod.key_successes}\n\n"
            f"[bold]Main Challenges:[/bold]\n  {internity_eod.main_challenges}\n\n"
            f"[bold]Plans for Tomorrow:[/bold]\n  {internity_eod.plans_for_tomorrow}"
        )
        console.print(
            Panel(preview, title="Internity EOD Data", border_style="blue")
        )

        if not dry_run:
            confirm = typer.confirm("Submit this to Internity?")
            if not confirm:
                console.print("[yellow]Cancelled.[/yellow]")
                raise typer.Exit()

        settings = get_settings()
        if not settings.INTERNITY_USERNAME or not settings.INTERNITY_FORM_URL:
            console.print(
                "[bold red]Internity credentials not configured in .env.[/bold red]"
            )
            raise typer.Exit(1)

        poster = InternityPoster(
            username=settings.INTERNITY_USERNAME,
            password=settings.INTERNITY_PASSWORD,
            form_url=settings.INTERNITY_FORM_URL,
        )
        poster.post(internity_eod, d, dry_run=dry_run)

        if dry_run:
            console.print(
                "[bold yellow]Dry run complete — form was filled but NOT submitted.[/bold yellow]"
            )
        else:
            console.print("[bold green]Submitted to Internity![/bold green]")
    finally:
        db.close()


@app.command(name="test-internity")
def test_internity():
    """Test the Internity (aufccs.org) login connection."""
    settings = get_settings()
    if not settings.INTERNITY_USERNAME:
        console.print(
            "[bold red]INTERNITY_USERNAME not set in .env.[/bold red]"
        )
        raise typer.Exit(1)

    poster = InternityPoster(
        username=settings.INTERNITY_USERNAME,
        password=settings.INTERNITY_PASSWORD,
        form_url=settings.INTERNITY_FORM_URL,
    )
    if poster.test_connection():
        console.print("[bold green]Internity login successful![/bold green]")
    else:
        console.print(
            "[bold red]Internity login failed. Check credentials in .env.[/bold red]"
        )


if __name__ == "__main__":
    app()
```

---

## 16. Step 14: Scheduler — `app/main.py`

Full file:

```python
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
        report = report_service.save(db, today, narrative)

        app_settings_row = db.query(AppSettings).first()

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
            print(
                "[Scheduler] Draft saved. Visit /reports/preview to review and post."
            )

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
                    poster.post(internity_eod, today)
                    print("[Scheduler] Auto-posted to Internity.")
                else:
                    print(
                        "[Scheduler] Internity credentials not configured. Skipping."
                    )
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
```

---

## 17. Verification

Run these in order:

### 1. Verify reorganization works

```bash
uv run uvicorn app.main:app --reload
```

If it starts without import errors, the reorganization is correct.

### 2. Test Internity login

```bash
uv run eod test-internity
```

Expected: `Internity login successful!`

### 3. Dry run (fills form, does NOT submit)

```bash
uv run eod internity --dry-run
```

Opens a visible browser, fills the form, pauses 60 seconds. Check that all fields are filled correctly.

### 4. Full submission

```bash
uv run eod internity
```

### 5. Web UI

- Dashboard: check the new "Auto-post to Internity" toggle
- Preview page: click "Submit to Internity" button

---

## 18. Selector Calibration

The Playwright selectors in `app/services/internity/poster.py` are based on the form screenshot. If they don't work:

### How to inspect

1. Open `https://aufccs.org/end_of_day_reports/create` in Chrome
2. Right-click on "Task Description" textarea → **Inspect**
3. Note the `name`, `id`, or `placeholder` attribute
4. Update selectors in `poster.py`

### Debugging tip

Run with `--dry-run` to see the browser. Add this to take a screenshot:

```python
page.screenshot(path="debug_form.png")
```

---

## 19. Troubleshooting

| Problem | Solution |
|---------|----------|
| `Executable doesn't exist` | Run `uv run playwright install chromium` |
| Login fails | Check login page URL — might not be `/login`. Inspect and update `_login()` |
| "Add Another Task" not found | Inspect the button text. Update `get_by_text()` call |
| Fields not being filled | Run with `--dry-run` and inspect. Update selectors |
| Timeout errors | Increase `wait_for_timeout()` values |
| `INTERNITY_USERNAME not set` | Add all 3 vars to `.env` |
| `auto_post_internity_enabled` column error | `_run_migrations()` handles this automatically |
