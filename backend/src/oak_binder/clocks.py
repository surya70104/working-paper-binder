"""The two clocks that hang off the report date (spec 3F, 3G, 8.7).

The database CHECK ``ck_binder_report_clocks`` re-verifies both values on every write, so
these functions must agree with PostgreSQL's date arithmetic. For ``+ INTERVAL '7 years'``
PostgreSQL keeps the day of month and clamps 29 February to 28 February.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

ASSEMBLY_DAYS = 60
RETENTION_YEARS = 7


def assembly_due(report_date: date) -> date:
    """Report date + 60 days: the SA 230 and NFRA assembly deadline."""
    return report_date + timedelta(days=ASSEMBLY_DAYS)


def retention_until(report_date: date) -> date:
    """Report date + 7 years, clamping 29 February to 28 February as PostgreSQL does."""
    year = report_date.year + RETENTION_YEARS
    day = min(report_date.day, calendar.monthrange(year, report_date.month)[1])
    return date(year, report_date.month, day)


def days_to_assembly(due: date, today: date) -> int:
    """Days left on the countdown; negative once the deadline has passed."""
    return (due - today).days
