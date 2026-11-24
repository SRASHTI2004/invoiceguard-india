"""MSME payment timer (Income-tax Act Section 43B(h) read with MSMED Act Section 15). GUIDANCE ONLY, not tax advice.

Amounts owed to a micro or small enterprise must be paid within 45 days of acceptance if there is a written agreement,
otherwise within 15 days. If paid later, the buyer's tax deduction for that expense is deferred to the year it is
actually paid. We start the clock on the invoice's 'accepted' date and warn when the limit is close.
"""
from datetime import date, timedelta

from . import timeutil

SOON_DAYS = 7  # warn when this many days or fewer are left
LIMIT_WITH_AGREEMENT = 45
LIMIT_WITHOUT_AGREEMENT = 15

NOTE = ("Guidance, not tax advice. Under Section 43B(h), sums owed to micro and small enterprises are deductible for the "
        "year only if paid within the legal limit (45 days with a written agreement, otherwise 15 days) from acceptance. "
        "Check with your accountant.")


def deadline(supplier, accepted_date: str | None, today: date | None = None) -> dict | None:
    """The pay-by date for an unpaid invoice from an MSME supplier, or None if the supplier is not micro or small."""
    if supplier is None or not supplier["msme"] or not accepted_date:
        return None
    try:
        accepted = date.fromisoformat(accepted_date)
    except ValueError:
        return None
    today = today or timeutil.today_ist()
    agreement = bool(supplier["msme_written_agreement"])
    limit = LIMIT_WITH_AGREEMENT if agreement else LIMIT_WITHOUT_AGREEMENT
    pay_by = accepted + timedelta(days=limit)
    left = (pay_by - today).days
    state = "overdue" if left < 0 else "soon" if left <= SOON_DAYS else "ok"
    when = ("is overdue by " + _days(-left)) if left < 0 else "is due today" if left == 0 else f"has {_days(left)} left"
    return {
        "class": supplier["msme"], "limit_days": limit,
        "basis": "written agreement" if agreement else "no written agreement",
        "accepted_date": accepted.isoformat(), "pay_by": pay_by.isoformat(), "days_left": left, "state": state,
        "message": f"{supplier['msme'].capitalize()} enterprise, {limit}-day limit ({'written agreement' if agreement else 'no written agreement'}): "
                   f"payment {when} (pay by {pay_by.day} {pay_by:%b %Y}).",
        "note": NOTE,
    }


def _days(n: int) -> str:
    return f"{n} day" + ("" if n == 1 else "s")
