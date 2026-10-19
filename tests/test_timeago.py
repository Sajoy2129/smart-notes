"""Tests for timeago.py. A fixed `now` keeps the results the same every run."""

from datetime import datetime

import pytest

from timeago import time_ago

NOW = datetime(2026, 10, 19, 12, 0, 0)


@pytest.mark.parametrize(
    "created, expected",
    [
        ("2026-10-19T11:59:30", "just now"),
        ("2026-10-19T12:00:05", "just now"),  # clock slightly behind: not "-1 minutes"
        ("2026-10-19T11:59:00", "1 minute ago"),
        ("2026-10-19T11:15:00", "45 minutes ago"),
        ("2026-10-19T11:00:00", "1 hour ago"),
        ("2026-10-19T10:00:00", "2 hours ago"),
        ("2026-10-18T11:00:00", "yesterday"),
        ("2026-10-16T12:00:00", "3 days ago"),
        ("2026-10-05T09:00:00", "5 Oct 2026"),
    ],
)
def test_time_ago(created, expected):
    assert time_ago(created, now=NOW) == expected
