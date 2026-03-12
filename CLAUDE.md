# CLAUDE.md

Project context for Claude Code.

## Project Overview

EOD Reporter -- automated daily End of Day report generator. Logs work activities, generates narrative EOD reports using a LangGraph agent with Gemini, posts to Microsoft Teams via Power Automate, and auto-fills the Internity (aufccs.org) EOD form via Playwright browser automation.

## Tech Stack

- **Python 3.12+** with **uv** package manager
- **FastAPI** web server with **Jinja2** templates and **HTMX** for dynamic UI
- **Typer** CLI (`eod` command)
- **LangGraph** + **LangChain** for agent orchestration
- **Gemini 2.5 Flash** (`langchain-google-genai`) as the LLM
- **SQLite** + **SQLAlchemy** (sync, declarative) for persistence
- **APScheduler** for scheduled report generation
- **Playwright** for Internity (aufccs.org) browser automation
- **httpx** for HTTP calls to Power Automate
- **Pydantic** / **pydantic-settings** for config and validation

## Architecture

Clean Architecture pattern with clear layer separation:

```
core/              → Config (pydantic-settings from .env), database engine/session
models/            → SQLAlchemy ORM (Activity, EODReport, AppSettings)
schemas/           → Pydantic request/response models
repositories/      → Data access (BaseRepository generic CRUD + specific repos)
services/teams/    → TeamsPoster (Power Automate HTTP post)
services/internity/ → InternityPoster (Playwright browser automation for aufccs.org)
agent/teams/       → LangGraph state machine for Teams EOD (nodes, graph, prompts, state)
agent/internity/   → Internity structured output (nodes, prompts) using .with_structured_output()
agent/llm.py       → Shared Gemini LLM singleton
api/v1/            → FastAPI endpoints (activities, reports, pages)
templates/         → Jinja2 HTML (base, dashboard, preview, history)
static/            → CSS ("Warm Terminal" design system)
```

## Key Patterns

- **Repository pattern**: `BaseRepository[ModelType]` with generic CRUD; specific repos add domain queries
- **Service layer**: Services use repositories, never access DB directly from endpoints
- **Dependency injection**: FastAPI `Depends()` for DB sessions and service instances
- **LangGraph agent (Teams)**: `fetch_activities → generate_draft → self_review → [revise | finalize] → END`
- **Structured output (Internity)**: `InternityEOD` Pydantic model via `.with_structured_output()` -- tasks, key_successes, main_challenges, plans_for_tomorrow
- **Prompt engineering**: `[Role]+[Expertise]+[Guidelines]+[Format]+[Constraints]`, CoT review, few-shot from `examples.json`
- **HTMX**: Delete buttons, auto-post toggle, schedule time picker (partial HTML swaps)
- **Settings in DB**: `AppSettings` single-row table for `auto_post_enabled`, `auto_post_internity_enabled`, `schedule_time`
- **Playwright automation**: Always headed (visible browser), `slow_mo=300` for watchability, user clicks Submit or `--auto-submit` flag

## Important Files

- `app/main.py` -- FastAPI app, APScheduler lifespan, `scheduled_eod_generation()`
- `app/agent/teams/graph.py` -- LangGraph `StateGraph` definition for Teams EOD
- `app/agent/teams/nodes.py` -- Node functions (fetch, generate, review, revise, finalize)
- `app/agent/teams/prompts.py` -- Teams prompt templates and formatting helpers
- `app/agent/internity/nodes.py` -- `generate_internity_eod()` structured output
- `app/agent/internity/prompts.py` -- Internity prompt template and few-shot example
- `app/agent/llm.py` -- `get_llm()` lazy Gemini singleton (shared by Teams and Internity)
- `app/schemas/report.py` -- `InternityEOD`, `InternityTask` Pydantic models
- `app/services/internity/poster.py` -- `InternityPoster` Playwright automation class
- `app/services/teams/poster.py` -- `TeamsPoster` Power Automate HTTP poster
- `app/core/config.py` -- `Settings` class loading from `.env`
- `app/api/v1/endpoints/reports.py` -- Report generation, posting, toggles
- `app/api/v1/endpoints/pages.py` -- HTML page routes (dashboard, preview, history)
- `app/cli.py` -- Typer CLI (`eod log`, `eod list`, `eod compile`, `eod post`, `eod internity`, `eod test-internity`)

## Running

```bash
# Web server
uv run uvicorn app.main:app --reload

# CLI
uv run eod log "activity description"
uv run eod compile
uv run eod post
uv run eod internity            # Opens browser, fills form, you click Submit
uv run eod internity --auto-submit  # Fills and submits automatically
uv run eod test-internity       # Test login (headless)
uv run eod test-internity --headed  # Debug selectors (visible browser + Inspector)
```

## Database

SQLite at `eod_reporter.db` (created automatically on first run). Tables are created by `init_db()` using `Base.metadata.create_all`. Column migration via `ensure_internity_column()` for `auto_post_internity_enabled`.

Three tables: `activities`, `eod_reports`, `app_settings`.

## Environment

Config via `.env` file (loaded by pydantic-settings):
- `GOOGLE_API_KEY` -- Gemini API key
- `POWER_AUTOMATE_URL` -- HTTP trigger URL with embedded SAS auth
- `EOD_SCHEDULE_TIME` -- Fallback schedule time (DB setting takes precedence)
- `MODEL_NAME` -- Gemini model name (default: `gemini-2.5-flash`)
- `INTERNITY_USERNAME` -- aufccs.org login email
- `INTERNITY_PASSWORD` -- aufccs.org login password
- `INTERNITY_FORM_URL` -- Full URL to the EOD form (e.g., `https://aufccs.org/end_of_day_reports/create`)

## Teams Integration

Posts to a group chat (not a channel) via Power Automate. The flow uses the Microsoft Teams connector's "Post message in a chat or channel" action with **Post as: User**.

## Internity Integration

Automates the aufccs.org EOD form using Playwright browser automation:
- Always opens a visible browser so the user can watch
- Fills tasks (description, hours, minutes), key successes, challenges, plans for tomorrow
- Waits for the user to click Submit or close the browser (unless `--auto-submit`)
- Scheduled auto-fill opens the browser at the configured time for manual review
- Login selectors calibrated: `#email`, `#password`, `button "Log in"`

## Frontend Design

"Warm Terminal" aesthetic using CSS custom properties:
- **Fonts**: DM Sans (body) + JetBrains Mono (timestamps/badges) via Google Fonts
- **Colors**: Warm stone palette with orange primary (#ea580c), semantic tokens (--primary, --muted, --accent, etc.)
- **Icons**: Lucide inline SVGs (no JS dependency)
- **Layout**: 960px max-width, two-column grid for Generate + Settings cards
- **Interactions**: fadeInUp card stagger, hover-reveal delete, spring toggle animation

## Conventions

- Endpoints return `RedirectResponse(status_code=303)` after form POSTs (POST-redirect-GET)
- HTMX endpoints return raw HTML snippets via `HTMLResponse`
- Date formatting uses `%#d` (Windows) for day without leading zero
- The scheduler reads time from the `app_settings` DB table, falling back to `.env`
- Scheduler rescheduling is done live via `scheduler.reschedule_job()` from the web UI
- Internity form selectors are calibrated to actual aufccs.org DOM -- update if site changes
