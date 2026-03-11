# CLAUDE.md

Project context for Claude Code.

## Project Overview

EOD Reporter -- automated daily End of Day report generator. Logs work activities, generates narrative EOD reports using a LangGraph agent with Gemini, and posts to a Microsoft Teams group chat via Power Automate.

## Tech Stack

- **Python 3.12+** with **uv** package manager
- **FastAPI** web server with **Jinja2** templates and **HTMX** for dynamic UI
- **Typer** CLI (`eod` command)
- **LangGraph** + **LangChain** for agent orchestration
- **Gemini 2.5 Flash** (`langchain-google-genai`) as the LLM
- **SQLite** + **SQLAlchemy** (sync, declarative) for persistence
- **APScheduler** for scheduled report generation
- **httpx** for HTTP calls to Power Automate
- **Pydantic** / **pydantic-settings** for config and validation

## Architecture

Clean Architecture pattern with clear layer separation:

```
core/        → Config (pydantic-settings from .env), database engine/session
models/      → SQLAlchemy ORM (Activity, EODReport, AppSettings)
schemas/     → Pydantic request/response models
repositories/ → Data access (BaseRepository generic CRUD + specific repos)
services/    → Business logic (ActivityService, ReportService, TeamsPoster)
agent/       → LangGraph state machine (nodes, graph, prompts, state)
api/v1/      → FastAPI endpoints (activities, reports, pages)
templates/   → Jinja2 HTML (base, dashboard, preview, history)
static/      → CSS
```

## Key Patterns

- **Repository pattern**: `BaseRepository[ModelType]` with generic CRUD; specific repos add domain queries
- **Service layer**: Services use repositories, never access DB directly from endpoints
- **Dependency injection**: FastAPI `Depends()` for DB sessions and service instances
- **LangGraph agent**: `fetch_activities → generate_draft → self_review → [revise | finalize] → END`
- **Structured output**: `ReviewResult` Pydantic model via `.with_structured_output()` for self-review
- **Prompt engineering**: `[Role]+[Expertise]+[Guidelines]+[Format]+[Constraints]`, CoT review, few-shot from `examples.json`
- **HTMX**: Used for delete buttons, auto-post toggle, and schedule time picker (partial HTML swaps, no full page reloads)
- **Settings in DB**: `AppSettings` single-row table for `auto_post_enabled` and `schedule_time` (editable from web UI)

## Important Files

- `app/main.py` -- FastAPI app, APScheduler lifespan, `scheduled_eod_generation()`
- `app/agent/graph.py` -- LangGraph `StateGraph` definition
- `app/agent/nodes.py` -- Node functions (fetch, generate, review, revise, finalize); `get_llm()` lazy singleton
- `app/agent/prompts.py` -- All prompt templates and formatting helpers
- `app/agent/examples.json` -- Few-shot EOD examples (3 real samples)
- `app/core/config.py` -- `Settings` class loading from `.env`
- `app/services/teams_service.py` -- Posts `{date, message}` JSON to Power Automate URL
- `app/api/v1/endpoints/reports.py` -- Report generation, posting, toggle auto-post, update schedule time
- `app/api/v1/endpoints/pages.py` -- HTML page routes (dashboard, preview, history)
- `app/cli.py` -- Typer CLI (`eod log`, `eod list`, `eod compile`, `eod post`)
- `docs/IMPLEMENTATION_GUIDE.md` -- Full implementation reference (2000+ lines)

## Running

```bash
# Web server
uv run uvicorn app.main:app --reload

# CLI
uv run eod log "activity description"
uv run eod compile
uv run eod post
```

## Database

SQLite at `eod_reporter.db` (created automatically on first run). Tables are created by `init_db()` using `Base.metadata.create_all`. No migrations -- delete the `.db` file to reset schema after model changes.

Three tables: `activities`, `eod_reports`, `app_settings`.

## Environment

Config via `.env` file (loaded by pydantic-settings):
- `GOOGLE_API_KEY` -- Gemini API key (passed explicitly to `ChatGoogleGenerativeAI`)
- `POWER_AUTOMATE_URL` -- HTTP trigger URL with embedded SAS auth
- `EOD_SCHEDULE_TIME` -- Fallback schedule time (DB setting takes precedence)
- `MODEL_NAME` -- Gemini model name (default: `gemini-2.5-flash`)

## Teams Integration

Posts to a group chat (not a channel) via Power Automate. The flow uses the Microsoft Teams connector's "Post message in a chat or channel" action with **Post as: User** (not Flow bot, which requires app installation that fails with federated users).

## Conventions

- Endpoints return `RedirectResponse(status_code=303)` after form POSTs (POST-redirect-GET)
- HTMX endpoints return raw HTML snippets via `HTMLResponse`
- Date formatting uses `%#d` (Windows) for day without leading zero
- The scheduler reads time from the `app_settings` DB table, falling back to `.env`
- Scheduler rescheduling is done live via `scheduler.reschedule_job()` from the web UI
