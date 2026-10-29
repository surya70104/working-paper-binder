"""The 60-day and 7-year clocks (spec 3F, 3G, 8.7). No database; the agreement with
PostgreSQL's arithmetic is proven in test_api_binders with a 29 February report date."""

from __future__ import annotations

from datetime import date, timedelta

from hypothesis import given
from hypothesis import strategies as st

from oak_binder.clocks import assembly_due, days_to_assembly, retention_until


def test_assembly_due_is_sixty_days_after_the_report_date() -> None:
    assert assembly_due(date(2026, 9, 30)) == date(2026, 11, 29)


def test_retention_is_seven_years_after_the_report_date() -> None:
    assert retention_until(date(2026, 9, 30)) == date(2033, 9, 30)


def test_leap_day_clamps_like_postgresql() -> None:
    assert retention_until(date(2028, 2, 29)) == date(2035, 2, 28)


def test_countdown_counts_down_and_goes_negative() -> None:
    due = date(2026, 11, 29)
    assert days_to_assembly(due, date(2026, 9, 30)) == 60
    assert days_to_assembly(due, date(2026, 11, 29)) == 0
    assert days_to_assembly(due, date(2026, 12, 1)) == -2


@given(st.dates(min_value=date(1990, 1, 1), max_value=date(2090, 12, 31)))
def test_clocks_always_land_after_the_report_date(report_date: date) -> None:
    assert assembly_due(report_date) - report_date == timedelta(days=60)
    retained = retention_until(report_date)
    assert retained.year == report_date.year + 7
    assert retained.month == report_date.month
    assert retained.day <= report_date.day
