"""Money helpers. All amounts are integer paise (1 rupee = 100 paise), never floats."""
from decimal import ROUND_HALF_UP, Decimal


def inr(paise: int) -> str:
    """Indian number formatting: 12400000 -> '₹1,24,000.00' (last three digits, then groups of two)."""
    sign = "-" if paise < 0 else ""
    rupees, p = divmod(abs(int(paise)), 100)
    digits = str(rupees)
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"{sign}₹{digits}.{p:02d}"


def to_paise(rupees) -> int | None:
    """Rupees (number or numeric string) -> paise, rounded half up. None if it is not a number."""
    if rupees is None or isinstance(rupees, bool):
        return None
    try:
        return int((Decimal(str(rupees)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return None
