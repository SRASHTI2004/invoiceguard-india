"""Indian Standard Time helpers. SQLite stores UTC ('YYYY-MM-DD HH:MM:SS'); everything a person reads is shown in IST.
India has no daylight saving, so a fixed +05:30 offset is exact (and needs no tz database on Windows)."""
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), "IST")


def parse_utc(value: str) -> datetime:
    """A SQLite 'YYYY-MM-DD HH:MM:SS' (UTC) timestamp -> an aware datetime."""
    return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def to_ist(value: str) -> str:
    """'2026-11-24 11:43:22' (UTC) -> '24 Nov 2026, 5:13 pm IST'."""
    d = parse_utc(value).astimezone(IST)
    return f"{d.day} {d:%b %Y}, {d.hour % 12 or 12}:{d:%M} {'am' if d.hour < 12 else 'pm'} IST"


def today_ist() -> date:
    return datetime.now(IST).date()
