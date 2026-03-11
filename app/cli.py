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


if __name__ == "__main__":
    app()
