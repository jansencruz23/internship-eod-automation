# EOD Reporter

An automated End of Day report generator for interns. Log work activities throughout the day, then let AI compile everything into polished EOD reports -- posted to Microsoft Teams and auto-filled on the Internity (aufccs.org) internship platform.

## How It Works

1. **Log activities** throughout the day (CLI or web UI) -- each entry is timestamped and auto-categorized into morning, afternoon, or evening
2. **At the scheduled time** (or manually), a LangGraph agent generates a narrative EOD report, self-reviews it, and revises if needed
3. **Preview and edit** the generated report in the web UI
4. **Post to Teams** with one click, or let auto-post handle it
5. **Submit to Internity** -- a browser opens, fills the aufccs.org form automatically, and waits for you to review and click Submit

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
| Internity Automation | Playwright (browser automation) |
| Package Manager | uv |

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Google AI Studio API key ([get one here](https://aistudio.google.com/apikey))
- Power Automate flow with HTTP trigger for Teams posting
- Playwright browsers: `uv run playwright install chromium`

## Setup

```bash
# Clone and install
git clone https://github.com/jansencruz23/internship-eod-automation.git
cd internship-eod-automation
uv sync

# Install Playwright browser
uv run playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API key from AI Studio | *required* |
| `POWER_AUTOMATE_URL` | Power Automate HTTP trigger URL | *required* |
| `INTERNITY_USERNAME` | aufccs.org login email | *required for Internity* |
| `INTERNITY_PASSWORD` | aufccs.org login password | *required for Internity* |
| `INTERNITY_FORM_URL` | Full URL to the Internity EOD form | *required for Internity* |
| `EOD_SCHEDULE_TIME` | Daily generation time (HH:MM) | `17:00` |
| `MODEL_NAME` | Gemini model to use | `gemini-2.5-flash` |

## Usage

### Web Interface

```bash
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000. The dashboard lets you:

- Log activities with the quick-entry form
- View activities grouped by time period (morning, afternoon, evening)
- Generate EOD reports on demand
- Preview, edit, and post reports to Teams
- Submit to Internity -- opens a visible browser, fills the form, you click Submit
- Configure scheduler time, Teams auto-post, and Internity auto-fill toggles

### CLI

```bash
# Log an activity
uv run eod log "Had team huddle for Project 2"

# Log with time period override
uv run eod log "Reviewed PRs" --time morning

# List today's activities
uv run eod list

# Generate an EOD report
uv run eod compile

# Post the report to Teams
uv run eod post

# Submit to Internity (opens browser, fills form, you click Submit)
uv run eod internity

# Submit to Internity automatically (no user interaction)
uv run eod internity --auto-submit

# Test Internity login
uv run eod test-internity

# Debug Internity selectors (opens visible browser with Inspector)
uv run eod test-internity --headed

# Test the Power Automate connection
uv run eod test-webhook
```

### Scheduler

The built-in scheduler (APScheduler) automatically generates EOD reports at the configured time. Adjust the time and toggles from the web UI -- no restart required.

- **Auto-post to Teams OFF** (default): Generates a draft. Visit `/reports/preview` to review and post.
- **Auto-post to Teams ON**: Generates and immediately posts to Teams.
- **Auto-fill Internity ON**: Opens a browser with the Internity form pre-filled for manual review and submission.

## Project Structure

```
app/
  core/              Config and database setup
  models/            SQLAlchemy ORM models (Activity, EODReport, AppSettings)
  schemas/           Pydantic models (InternityEOD, InternityTask)
  repositories/      Data access layer (generic base + specific repos)
  services/teams/    TeamsPoster (Power Automate HTTP post)
  services/internity/ InternityPoster (Playwright browser automation)
  agent/teams/       LangGraph agent for Teams EOD (nodes, graph, prompts, state)
  agent/internity/   Internity structured output (nodes, prompts)
  agent/llm.py       Shared Gemini LLM singleton
  api/v1/            FastAPI endpoints and page routes
  templates/         Jinja2 HTML templates
  static/            CSS ("Warm Terminal" design system)
  cli.py             Typer CLI entry point
  main.py            FastAPI app with scheduler lifespan
docs/
  IMPLEMENTATION_GUIDE.md       Teams integration reference
  INTERNITY_INTEGRATION.md      Internity integration reference
```

## Agent Architecture

### Teams EOD (Narrative Report)

The LangGraph agent follows a generate-review-revise pattern:

```
fetch_activities -> generate_draft -> self_review -> [revise or finalize] -> END
```

- **fetch_activities**: Pulls activities from the database, groups by time period
- **generate_draft**: Uses few-shot examples and activities to generate a narrative EOD
- **self_review**: Structured output (`ReviewResult`) evaluates the draft against quality criteria
- **revise_draft**: If review fails, revises based on feedback (max 2 revision cycles)
- **finalize**: Copies the approved draft to the final output

### Internity EOD (Structured Form)

Uses `.with_structured_output()` to generate `InternityEOD` directly:

- **Tasks**: Description + hours + minutes for each task
- **Key Successes**: Accomplishments for the day
- **Main Challenges**: Difficulties encountered
- **Plans for Tomorrow**: Next steps

## Power Automate Setup

Since group chats don't support incoming webhooks, the app posts through a Power Automate flow:

1. Create a new flow with **"When an HTTP request is received"** trigger
2. Add **"Post message in a chat or channel"** action (Microsoft Teams connector)
   - Post as: **User**
   - Post in: Your group chat
   - Message: Use dynamic content (`date` and `message` fields)
3. Copy the trigger URL to `.env` as `POWER_AUTOMATE_URL`

## License

Private project.
