"""Turn a saved timestamp into friendly text like '2 hours ago'."""

from datetime import datetime


def _plural(count, word):
    """_plural(1, 'hour') -> '1 hour', _plural(3, 'hour') -> '3 hours'."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def time_ago(iso_text, now=None):
    """'2026-10-19T10:00:00' -> 'just now', '5 minutes ago', 'yesterday', ...

    Older than a week shows the date instead, e.g. '12 Oct 2026'.
    `now` can be passed in so tests always get the same answer.
    """
    created = datetime.fromisoformat(iso_text)
    now = now or datetime.now()
    seconds = (now - created).total_seconds()

    if seconds < 60:  # also covers a clock that is slightly behind
        return "just now"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{_plural(minutes, 'minute')} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{_plural(hours, 'hour')} ago"
    days = hours // 24
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return f"{created.day} {created:%b %Y}"
