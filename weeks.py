"""Turn a due date into a short label with its week number."""

from datetime import date


def week_label(iso_date):
    """Return e.g. "23 Oct, week 43" for "2026-10-23", or None if there's no valid date.

    Uses ISO week numbers: weeks start on Monday, and week 1 is the week
    containing the year's first Thursday. So 29 Dec 2025 is in week 1 (of 2026).
    """
    try:
        day = date.fromisoformat(iso_date)
    except (TypeError, ValueError):  # None, or text that isn't a YYYY-MM-DD date
        return None
    week = day.isocalendar().week
    return f"{day.day} {day:%b}, week {week}"
