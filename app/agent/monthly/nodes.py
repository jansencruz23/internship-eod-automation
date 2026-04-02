from datetime import date
from calendar import monthrange

from app.agent.llm import get_llm
from app.agent.monthly.prompts import WEEKLY_SUMMARY_PROMPT
from app.models.report import EODReport


def group_reports_by_week(reports: list[EODReport], year: int, month: int) -> list[dict]:
    """Group reports into work weeks (Mon-Fri) within the month."""
    if not reports:
        return []

    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])

    # Find all Monday-start work weeks that overlap this month
    weeks = []
    # Start from the first day of the month
    current = first_day
    week_num = 1

    while current <= last_day:
        # Find the Monday of this week (or month start if it's mid-week)
        if current == first_day:
            week_start = current
        else:
            # Jump to next Monday
            days_until_monday = (7 - current.weekday()) % 7
            if days_until_monday == 0:
                week_start = current
            else:
                week_start = current
                # This shouldn't happen in our loop logic

        # Find Friday of this week (or month end)
        days_until_friday = (4 - week_start.weekday()) % 7
        if week_start.weekday() > 4:
            # Weekend start — skip to next Monday
            days_to_monday = (7 - week_start.weekday()) % 7
            current = date.fromordinal(week_start.toordinal() + days_to_monday)
            continue

        week_end = date.fromordinal(
            min(
                week_start.toordinal() + days_until_friday,
                last_day.toordinal(),
            )
        )

        # Collect reports in this range
        week_reports = [
            r for r in reports if week_start <= r.date <= week_end
        ]

        if week_reports:
            weeks.append(
                {
                    "week_number": week_num,
                    "start_date": week_start,
                    "end_date": week_end,
                    "reports": week_reports,
                }
            )
            week_num += 1

        # Move to next Monday
        current = date.fromordinal(week_end.toordinal() + 1)
        # Skip weekend
        while current <= last_day and current.weekday() > 4:
            current = date.fromordinal(current.toordinal() + 1)

    return weeks


def _format_daily_reports(reports: list[EODReport]) -> str:
    lines = []
    for r in reports:
        day_name = r.date.strftime("%A")
        date_str = r.date.strftime("%B %d")
        lines.append(f"{day_name}, {date_str}:\n{r.narrative}")
    return "\n\n".join(lines)


def generate_weekly_summary(
    week_number: int,
    date_range: str,
    reports: list[EODReport],
) -> str:
    """Generate a summary for one week using the LLM."""
    llm = get_llm()
    daily_text = _format_daily_reports(reports)

    chain = WEEKLY_SUMMARY_PROMPT | llm
    result = chain.invoke(
        {
            "week_number": week_number,
            "date_range": date_range,
            "daily_reports": daily_text,
        }
    )
    return result.content.strip()


def generate_monthly_summary(
    reports: list[EODReport], year: int, month: int
) -> list[dict]:
    """Generate weekly summaries for an entire month.

    Returns a list of dicts with week_number, date_range, and summary.
    """
    weeks = group_reports_by_week(reports, year, month)
    results = []

    for week in weeks:
        start_str = week["start_date"].strftime("%b %d")
        end_str = week["end_date"].strftime("%b %d")
        date_range = f"{start_str} - {end_str}"

        summary = generate_weekly_summary(
            week_number=week["week_number"],
            date_range=date_range,
            reports=week["reports"],
        )

        results.append(
            {
                "week_number": week["week_number"],
                "start_date": week["start_date"],
                "end_date": week["end_date"],
                "date_range": date_range,
                "summary": summary,
                "report_count": len(week["reports"]),
            }
        )

    return results