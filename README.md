# EOD Reporter

An automated End of Day (EOD) report generator that compiles daily work activities into narrative-style summaries and posts them to a Microsoft Teams group chat.

Log activities throughout the day via CLI or web interface. At a scheduled time, a LangGraph agent powered by Gemini compiles everything into a polished EOD report matching your team's writing style, reviews it for quality, and optionally auto-posts to Teams via Power Automate.

## How It Works

1. **Log activities** throughout the day (CLI or web UI) -- each entry is timestamped and auto-categorized into morning, afternoon, or evening
2. **At the scheduled time** (or manually), the LangGraph agent fetches all activities, generates a narrative draft, self-reviews it, and revises if needed
3. **Preview and edit** the generated report in the web UI
4. **Post to Teams** with one click, or let auto-post handle it

## Tech Stack

| Component | Technology |
|---|---|
| LLM | Gemini 2.5 Flash via `langchain-google-genai` |
| Agent Framework | LangGraph (stateful graph with self-review loop) |
| Web Framework | FastAPI + Jinja2 + HTMX |
| CLI | Typer + Rich |
| Database | SQLite + SQLAlchemy |
| Scheduler | APScheduler |
| Teams Integration | Power Automate HTTP trigger |
| Package Manager | uv |

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Google AI Studio API key ([get one here](https://aistudio.google.com/apikey))
- Power Automate flow with HTTP trigger configured to post to your Teams group chat

## Setup

```bash
# Clone and install
git clone <repo-url>
cd internity
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your API key and Power Automate URL
```

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API key from AI Studio | *required* |
| `POWER_AUTOMATE_URL` | Power Automate HTTP trigger URL | *required* |
| `EOD_SCHEDULE_TIME` | Daily generation time (HH:MM) | `17:00` |
| `MODEL_NAME` | Gemini model to use | `gemini-2.5-flash` |

## Usage

### Web Interface

```bash
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000. The dashboard lets you:

- Log activities with the quick-entry form
- View activities grouped by time period
- Generate EOD reports on demand
- Preview, edit, and post reports to Teams
- Configure the scheduler time and auto-post toggle

### CLI

```bash
# Log an activity
uv run eod log "Had team huddle for Project 2"

# Log with time period override
uv run eod log "Reviewed PRs" --time morning

# List today's activities
uv run eod list

# List activities for a specific date
uv run eod list --date 2025-03-10

# Generate an EOD report
uv run eod compile

# Post the report to Teams
uv run eod post

# Test the Power Automate connection
uv run eod test-webhook
```

### Scheduler

The app includes a built-in scheduler (APScheduler) that automatically generates an EOD report at the configured time. You can adjust both the time and auto-post behavior from the web UI's Scheduler Settings card -- no restart required.

- **Auto-post OFF** (default): Generates a draft and saves it. Visit `/reports/preview` to review and post manually.
- **Auto-post ON**: Generates and immediately posts to Teams.

## Project Structure

```
app/
  core/           Config and database setup
  models/         SQLAlchemy ORM models (Activity, EODReport, AppSettings)
  schemas/        Pydantic validation schemas
  repositories/   Data access layer (generic base + specific repos)
  services/       Business logic (activity, report, Teams posting)
  agent/          LangGraph agent (state, nodes, graph, prompts, examples)
  api/v1/         FastAPI endpoints and page routes
  templates/      Jinja2 HTML templates
  static/         CSS
  cli.py          Typer CLI entry point
  main.py         FastAPI app with scheduler lifespan
docs/
  IMPLEMENTATION_GUIDE.md   Full step-by-step implementation reference
```

## Agent Architecture

The LangGraph agent follows a generate-review-revise pattern:

```
fetch_activities -> generate_draft -> self_review -> [revise or finalize] -> END
```

- **fetch_activities**: Pulls activities from the database, groups by time period
- **generate_draft**: Uses few-shot examples and activities to generate a narrative EOD
- **self_review**: Structured output (Pydantic `ReviewResult`) evaluates the draft against 6 quality criteria
- **revise_draft**: If review fails, revises based on feedback (max 2 revision cycles)
- **finalize**: Copies the approved draft to the final output

Prompts follow the `[Role] + [Expertise] + [Guidelines] + [Format] + [Constraints]` pattern with Chain-of-Thought reasoning in the review step and few-shot examples externalized to `examples.json`.

## Power Automate Setup

Since group chats don't support incoming webhooks, the app posts through a Power Automate flow:

1. Create a new flow with **"When an HTTP request is received"** trigger
2. Add **"Post message in a chat or channel"** action (Microsoft Teams connector)
   - Post as: **User**
   - Post in: Your group chat
   - Message: Use dynamic content from the trigger body (`date` and `message` fields)
3. Copy the trigger URL to your `.env` as `POWER_AUTOMATE_URL`

The app sends a JSON payload: `{"date": "March 11, 2026", "message": "...the narrative..."}`.

## License

Private project.
