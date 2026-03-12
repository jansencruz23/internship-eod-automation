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
    auto_submit: bool = typer.Option(
        False,
        "--auto-submit",
        help="Submit automatically without asking (skips browser confirm dialog)",
    ),
):
    """Submit the EOD report to Internity (aufccs.org).

    Opens a visible browser so you can watch the form being filled.
    A confirm dialog appears before submitting (unless --auto-submit is used).
    """
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
            f"  [{t.hours}h {t.minutes}m] {t.description}" for t in internity_eod.tasks
        )
        preview = (
            f"[bold]Tasks:[/bold]\n{tasks_text}\n\n"
            f"[bold]Key Successes:[/bold]\n  {internity_eod.key_successes}\n\n"
            f"[bold]Main Challenges:[/bold]\n  {internity_eod.main_challenges}\n\n"
            f"[bold]Plans for Tomorrow:[/bold]\n  {internity_eod.plans_for_tomorrow}"
        )
        console.print(Panel(preview, title="Internity EOD Data", border_style="blue"))

        settings = get_settings()
        if not settings.INTERNITY_USERNAME or not settings.INTERNITY_FORM_URL:
            console.print(
                "[bold red]Internity credentials not configured in .env.[/bold red]"
            )
            raise typer.Exit(1)

        console.print(
            "\n[bold]Opening browser — watch the form being filled...[/bold]"
        )

        poster = InternityPoster(
            username=settings.INTERNITY_USERNAME,
            password=settings.INTERNITY_PASSWORD,
            form_url=settings.INTERNITY_FORM_URL,
        )
        submitted = poster.post(internity_eod, d, auto_submit=auto_submit)

        if submitted:
            console.print("[bold green]Submitted to Internity![/bold green]")
        else:
            console.print("[bold yellow]Submission cancelled.[/bold yellow]")
    finally:
        db.close()


@app.command(name="test-internity")
def test_internity(
    headed: bool = typer.Option(
        False, "--headed", help="Launch visible browser with Inspector for debugging selectors"
    ),
):
    """Test the Internity (aufccs.org) login connection."""
    settings = get_settings()
    if not settings.INTERNITY_USERNAME:
        console.print("[bold red]INTERNITY_USERNAME not set in .env.[/bold red]")
        raise typer.Exit(1)

    poster = InternityPoster(
        username=settings.INTERNITY_USERNAME,
        password=settings.INTERNITY_PASSWORD,
        form_url=settings.INTERNITY_FORM_URL,
    )
    if poster.test_connection(headed=headed):
        console.print("[bold green]Internity login successful![/bold green]")
    else:
        console.print(
            "[bold red]Internity login failed. Check credentials in .env.[/bold red]"
        )


if __name__ == "__main__":
    app()
