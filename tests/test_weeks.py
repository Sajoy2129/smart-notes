import pytest

from weeks import week_label


def test_normal_date():
    assert week_label("2026-10-23") == "23 Oct, week 43"


def test_single_digit_day_has_no_leading_zero():
    assert week_label("2026-11-05") == "5 Nov, week 45"


# parametrize runs the same test once for each pair of values.
@pytest.mark.parametrize(
    "iso_date, expected",
    [
        ("2025-12-29", "29 Dec, week 1"),   # Monday: already week 1 of 2026
        ("2026-12-31", "31 Dec, week 53"),  # 2026 has 53 weeks
        ("2027-01-03", "3 Jan, week 53"),   # Sunday: still the last week of 2026
        ("2027-01-04", "4 Jan, week 1"),    # Monday: week 1 of 2027
    ],
)
def test_year_boundaries(iso_date, expected):
    assert week_label(iso_date) == expected


@pytest.mark.parametrize("bad_value", [None, "", "next Friday", "2026-13-01", "2026-02-30"])
def test_missing_or_invalid_date_returns_none(bad_value):
    assert week_label(bad_value) is None
