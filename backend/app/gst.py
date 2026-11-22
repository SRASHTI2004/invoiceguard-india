"""India GST checks. Plain code, no LLM, no network.

Everything here is a pure function over the extracted invoice dict (amounts in paise), so it is easy to test.
Each check returns a GstResult (passed or failed) so the dashboard can show a full per-invoice GST report.

Invoice dict fields used: supplier_gstin, buyer_gstin, place_of_supply, taxable_paise, cgst_paise, sgst_paise,
igst_paise, total_paise, line_items = [{"description", "hsn", "qty", "unit_paise", "gst_rate"}].
"""
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .money import inr

BLOCK = "BLOCK"
HOLD = "HOLD"

GSTIN_RE = re.compile(r"^(\d{2})([A-Z]{5}\d{4}[A-Z])([1-9A-Z])Z([0-9A-Z])$")
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
VALID_RATES = {Decimal(r) for r in ("0", "0.25", "3", "5", "12", "18", "28")}  # GST slabs
TOLERANCE_PAISE = 100  # rounding tolerance: Rs 1 per tax component / total

STATES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura",
    "17": "Meghalaya", "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat", "26": "Dadra & Nagar Haveli and Daman & Diu",
    "27": "Maharashtra", "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman & Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh",
    "38": "Ladakh", "97": "Other Territory", "99": "Centre Jurisdiction",
}


@dataclass
class GstResult:
    code: str
    label: str            # short title for the dashboard, e.g. "Supplier GSTIN"
    ok: bool
    message: str          # plain-English detail
    severity: str = HOLD  # what a failure means: BLOCK (looks like fraud) or HOLD (needs a person)

    def as_dict(self) -> dict:
        return {"code": self.code, "label": self.label, "ok": self.ok, "message": self.message,
                "severity": None if self.ok else self.severity}


# ---- GSTIN -------------------------------------------------------------------------------------------------------
def gstin_check_char(first14: str) -> str:
    """The 15th GSTIN character: a mod-36 check over the first 14 (weights 1,2,1,2,...)."""
    total = 0
    for i, ch in enumerate(first14):
        product = _CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return _CHARS[(36 - total % 36) % 36]


def make_gstin(state_code: str, pan: str, entity: str = "1") -> str:
    """Build a GSTIN with the correct check character (used for the fictional sample data)."""
    body = f"{state_code}{pan}{entity}Z"
    return body + gstin_check_char(body)


def validate_gstin(gstin: str | None) -> tuple[bool, str]:
    """(ok, explanation). Checks format, state code and the check character."""
    g = (gstin or "").strip().upper()
    if not g:
        return False, "no GSTIN on the invoice"
    m = GSTIN_RE.match(g)
    if not m:
        return False, f"{g} is not in the 15-character GSTIN format (2 digits, PAN, entity, Z, check character)"
    if m.group(1) not in STATES:
        return False, f"{g} has an unknown state code {m.group(1)}"
    expected = gstin_check_char(g[:14])
    if g[14] != expected:
        return False, f"{g} fails the GSTIN check character (should end in {expected}): the number is not real"
    return True, f"{g} ({STATES[g[:2]]})"


def state_code_of(gstin: str | None) -> str | None:
    g = (gstin or "").strip().upper()
    return g[:2] if GSTIN_RE.match(g) and g[:2] in STATES else None


def parse_place_of_supply(text: str | None) -> str | None:
    """'29-Karnataka', 'Karnataka (29)', 'Karnataka' or '29' -> '29'. None if unrecognised."""
    t = (text or "").strip().lower()
    if not t:
        return None
    m = re.search(r"\b(\d{2})\b", t)
    if m and m.group(1) in STATES:
        return m.group(1)
    t = t.replace("&", "and")
    for code, name in sorted(STATES.items(), key=lambda kv: -len(kv[1])):  # longest names first
        if name.lower().replace("&", "and") in t:
            return code
    return None


def state_name(code: str | None) -> str:
    return STATES.get(code or "", "unknown state")


# ---- tax arithmetic ----------------------------------------------------------------------------------------------
def _dec(v) -> Decimal | None:
    try:
        return Decimal(str(v))
    except Exception:
        return None


def line_taxable(item: dict) -> int:
    return int(item["qty"]) * int(item["unit_paise"])


def expected_tax_paise(items: list[dict]) -> int:
    """Total GST implied by the line items (each line's own rate), rounded half-up to the paisa."""
    exact = Decimal(0)
    for it in items:
        exact += Decimal(line_taxable(it)) * Decimal(str(it["gst_rate"])) / 100
    return int(exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _near(a: int, b: int) -> bool:
    return abs(a - b) <= TOLERANCE_PAISE


def _items_readable(items) -> bool:
    try:
        for it in items:
            line_taxable(it)
            if _dec(it.get("gst_rate")) is None:
                return False
    except (KeyError, TypeError, ValueError):
        return False
    return bool(items)


# ---- the checks --------------------------------------------------------------------------------------------------
def gstin_results(inv: dict, buyer_gstin: str, saved_supplier_gstin: str | None) -> list[GstResult]:
    out = []
    ok, why = validate_gstin(inv.get("supplier_gstin"))
    out.append(GstResult("supplier_gstin_invalid", "Supplier GSTIN", ok,
                         ("Valid: " if ok else "Not a real GSTIN: ") + why, BLOCK))
    if ok and saved_supplier_gstin:
        same = inv["supplier_gstin"].strip().upper() == saved_supplier_gstin.strip().upper()
        out.append(GstResult("supplier_gstin_mismatch", "GSTIN matches saved supplier", same,
                             "Matches the GSTIN saved for this supplier" if same else
                             f"Invoice GSTIN {inv['supplier_gstin']} differs from the saved GSTIN {saved_supplier_gstin}",
                             BLOCK))
    bok, bwhy = validate_gstin(inv.get("buyer_gstin"))
    if bok and inv["buyer_gstin"].strip().upper() == buyer_gstin:
        out.append(GstResult("buyer_gstin_mismatch", "Buyer GSTIN", True, f"Billed to our GSTIN {buyer_gstin}"))
    else:
        detail = bwhy if not bok else f"billed to {inv['buyer_gstin']}, not our GSTIN {buyer_gstin}"
        out.append(GstResult("buyer_gstin_mismatch", "Buyer GSTIN", False,
                             f"Invoice is not billed to our GSTIN ({detail}); we could not claim input tax credit"))
    return out


def hsn_results(items: list[dict]) -> list[GstResult]:
    bad = [str(i.get("description") or "item")[:30] for i in items
           if not re.fullmatch(r"\d{4}|\d{6}|\d{8}", str(i.get("hsn") or "").strip())]
    if bad:
        return [GstResult("hsn_invalid", "HSN / SAC codes", False,
                          "Missing or malformed HSN/SAC (needs 4, 6 or 8 digits) for: " + ", ".join(bad))]
    codes = ", ".join(sorted({str(i["hsn"]).strip() for i in items}))
    return [GstResult("hsn_invalid", "HSN / SAC codes", True, f"All lines carry a valid code ({codes})")]


def tax_type_result(inv: dict) -> GstResult:
    label = "CGST+SGST vs IGST"
    sup = state_code_of(inv.get("supplier_gstin"))
    pos = parse_place_of_supply(inv.get("place_of_supply"))
    if sup is None:
        return GstResult("wrong_tax_type", label, False, "Cannot tell the supplier's state (GSTIN invalid)")
    if pos is None:
        return GstResult("place_of_supply_unknown", "Place of supply", False,
                         f"Place of supply '{inv.get('place_of_supply') or ''}' is missing or not a known state")
    amounts = [inv.get(k) for k in ("cgst_paise", "sgst_paise", "igst_paise")]
    if all(a is None for a in amounts):
        return GstResult("wrong_tax_type", label, False, "No GST amounts found on the invoice")
    cgst, sgst, igst = (a or 0 for a in amounts)
    intra = sup == pos
    where = f"supplier in {state_name(sup)}, place of supply {state_name(pos)}"
    if intra and igst == 0 and cgst > 0 and sgst > 0:
        return GstResult("wrong_tax_type", label, True, f"Same state ({where}): CGST + SGST charged, as required")
    if not intra and igst > 0 and cgst == 0 and sgst == 0:
        return GstResult("wrong_tax_type", label, True, f"Different states ({where}): IGST charged, as required")
    need = "CGST + SGST" if intra else "IGST"
    return GstResult("wrong_tax_type", label, False,
                     f"Wrong tax type: {where}, so {need} applies, but the invoice charges "
                     f"CGST {inr(cgst)}, SGST {inr(sgst)}, IGST {inr(igst)}")


def arithmetic_results(inv: dict) -> list[GstResult]:
    items = inv.get("line_items") or []
    if not _items_readable(items):
        return [GstResult("gst_arithmetic", "GST arithmetic", False, "Line items or GST rates could not be read")]
    out = []
    bad_rates = sorted({str(i["gst_rate"]) for i in items if _dec(i["gst_rate"]) not in VALID_RATES})
    out.append(GstResult("gst_rate_invalid", "GST rate slabs", not bad_rates,
                         "All rates are valid GST slabs (0, 0.25, 3, 5, 12, 18, 28%)" if not bad_rates else
                         "Not a valid GST rate: " + ", ".join(r + "%" for r in bad_rates)))
    taxable = sum(line_taxable(i) for i in items)
    stated = inv.get("taxable_paise")
    out.append(GstResult("taxable_mismatch", "Taxable value", stated == taxable,
                         f"Line items add up to the stated taxable value {inr(taxable)}" if stated == taxable else
                         f"Line items add up to {inr(taxable)} but the invoice states taxable value "
                         f"{inr(stated) if isinstance(stated, int) else 'nothing'}"))
    exp_tax = expected_tax_paise(items)
    cg, sg, ig = (inv.get(k) or 0 for k in ("cgst_paise", "sgst_paise", "igst_paise"))
    stated_tax = cg + sg + ig
    tax_ok = _near(stated_tax, exp_tax)
    out.append(GstResult("gst_amount_wrong", "GST amount", tax_ok,
                         f"GST of {inr(stated_tax)} matches the line-item rates" if tax_ok else
                         f"At the stated rates GST should be {inr(exp_tax)} but the invoice charges {inr(stated_tax)}"))
    if cg or sg:
        even = _near(cg, sg)
        out.append(GstResult("cgst_sgst_unequal", "CGST = SGST", even,
                             "CGST and SGST are equal halves" if even else
                             f"CGST {inr(cg)} and SGST {inr(sg)} must be equal"))
    total = inv.get("total_paise")
    exp_total = taxable + exp_tax
    total_ok = isinstance(total, int) and _near(total, exp_total)
    out.append(GstResult("gst_total_wrong", "Invoice total", total_ok,
                         f"Total {inr(total)} = taxable {inr(taxable)} + GST {inr(exp_tax)}" if total_ok else
                         f"Invoice total {inr(total) if isinstance(total, int) else 'missing'} is wrong: "
                         f"taxable {inr(taxable)} + GST {inr(exp_tax)} = {inr(exp_total)}"))
    return out


def run_gst_checks(inv: dict, buyer_gstin: str, saved_supplier_gstin: str | None = None) -> list[GstResult]:
    """The full per-invoice GST report (passes and failures), in display order."""
    items = inv.get("line_items") or []
    results = gstin_results(inv, buyer_gstin, saved_supplier_gstin)
    results.append(tax_type_result(inv))
    results += hsn_results(items)
    results += arithmetic_results(inv)
    return results
