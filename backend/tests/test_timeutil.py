from datetime import date

from app import checks, timeutil
from tests.test_checks import conn, good_invoice, save  # noqa: F401  (fixtures)


def test_utc_to_ist_conversion():
    assert timeutil.to_ist("2026-11-24 11:43:22") == "24 Nov 2026, 5:13 pm IST"
    assert timeutil.to_ist("2026-11-24 00:00:00") == "24 Nov 2026, 5:30 am IST"
    assert timeutil.to_ist("2026-11-24 18:30:00") == "25 Nov 2026, 12:00 am IST"  # rolls to the next IST day
    assert timeutil.to_ist("2026-01-05 06:35:00") == "5 Jan 2026, 12:05 pm IST"


def test_today_ist_is_a_date():
    assert isinstance(timeutil.today_ist(), date)


def test_daily_limit_uses_the_ist_day(conn):  # noqa: F811
    # 20:00 UTC on 5 Nov is 01:30 IST on 6 Nov: it counts towards 6 Nov, not 5 Nov
    save(conn, good_invoice(invoice_number="A", invoice_date="2026-01-01"), "PAID", "2026-11-05 20:00:00")
    assert checks.paid_today_paise(conn, "2026-11-06") == 17717800
    assert checks.paid_today_paise(conn, "2026-11-05") == 0
