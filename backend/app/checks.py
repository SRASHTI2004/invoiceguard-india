"""Deterministic fraud checks: plain code, no LLM, no network.

An invoice is a dict (see gst.py and extract.normalize): supplier_name, supplier_gstin, buyer_gstin, place_of_supply,
invoice_number, invoice_date, po_number, taxable/cgst/sgst/igst/total in paise, payee_upi / payee_account / payee_ifsc,
line_items = [{"description", "hsn", "qty", "unit_paise", "gst_rate"}].
Each check returns a list of Findings. BLOCK = looks like fraud, HOLD = needs a human.
"""
import sqlite3
from dataclasses import dataclass

from . import businesses, config, gst, timeutil
from .money import inr

BLOCK = "BLOCK"
HOLD = "HOLD"

REQUIRED_FIELDS = ["supplier_name", "invoice_number", "invoice_date", "total_paise"]

money = inr  # all amounts are shown in rupees with Indian digit grouping


@dataclass
class Finding:
    code: str
    severity: str  # BLOCK or HOLD
    message: str


def check_extraction(inv: dict) -> list[Finding]:
    """Required fields present and every line item readable. (GST arithmetic is checked in gst.py.)"""
    missing = [f for f in REQUIRED_FIELDS if inv.get(f) in (None, "") or
               (f == "total_paise" and (not isinstance(inv.get(f), int) or isinstance(inv.get(f), bool)))]
    if not (inv.get("payee_upi") or (inv.get("payee_account") and inv.get("payee_ifsc"))):
        missing.append("payment details (UPI ID or bank account + IFSC)")
    if missing:
        return [Finding("missing_fields", HOLD, f"Extraction is missing required fields: {', '.join(missing)}")]
    items = inv.get("line_items") or []
    if not items:
        return [Finding("no_line_items", HOLD, "Invoice has no line items")]
    for i in items:
        if not isinstance(i.get("qty"), int) or not isinstance(i.get("unit_paise"), int) \
                or not isinstance(i.get("gst_rate"), (int, float)):
            return [Finding("bad_line_items", HOLD, "Line items could not be read (quantity, price or GST rate missing)")]
    return []


def get_supplier(conn: sqlite3.Connection, name: str, business_id: int = 1):
    """A supplier of THIS business only: another client's supplier is unknown here."""
    return conn.execute("SELECT * FROM suppliers WHERE lower(name) = lower(?) AND business_id = ?",
                        (name.strip(), business_id)).fetchone()


def check_supplier(supplier, name: str) -> list[Finding]:
    if supplier is None:
        return [Finding("unknown_supplier", BLOCK, f"'{name}' is not a known supplier")]
    if not supplier["approved"]:
        return [Finding("unapproved_supplier", BLOCK, f"Supplier '{supplier['name']}' is not on the approved list")]
    return []


def check_duplicate(conn, inv: dict, supplier_id: int, exclude_id: int | None = None) -> list[Finding]:
    """Same supplier + invoice number, or same supplier + amount + date, already recorded."""
    excl = exclude_id if exclude_id is not None else -1
    row = conn.execute(
        "SELECT id FROM invoices WHERE supplier_id = ? AND id != ? AND lower(invoice_number) = lower(?)",
        (supplier_id, excl, inv["invoice_number"])).fetchone()
    if row:
        return [Finding("duplicate_number", BLOCK,
                        f"Duplicate: invoice {inv['invoice_number']} from this supplier was already received (#{row['id']})")]
    row = conn.execute(
        "SELECT id FROM invoices WHERE supplier_id = ? AND id != ? AND total_paise = ? AND invoice_date = ?",
        (supplier_id, excl, inv["total_paise"], inv["invoice_date"])).fetchone()
    if row:
        return [Finding("duplicate_amount_date", BLOCK,
                        f"Duplicate: same supplier, amount {money(inv['total_paise'])} and date as invoice #{row['id']}")]
    return []


def check_po(conn, inv: dict, supplier_id: int) -> list[Finding]:
    po_number = inv.get("po_number")
    if not po_number:
        return [Finding("no_po", HOLD, "Invoice does not reference a purchase order")]
    po = conn.execute("SELECT * FROM purchase_orders WHERE lower(po_number) = lower(?)", (po_number.strip(),)).fetchone()
    if po is None:
        return [Finding("po_not_found", BLOCK, f"Purchase order {po_number} does not exist")]
    if po["supplier_id"] != supplier_id:
        return [Finding("po_wrong_supplier", BLOCK, f"Purchase order {po_number} belongs to a different supplier")]
    if inv["total_paise"] > po["amount_paise"]:
        return [Finding("over_po", BLOCK,
                        f"Invoice total {money(inv['total_paise'])} is more than the PO amount {money(po['amount_paise'])}")]
    if inv["total_paise"] < po["amount_paise"]:
        return [Finding("under_po", HOLD,
                        f"Invoice total {money(inv['total_paise'])} is less than the PO amount {money(po['amount_paise'])}")]
    return []


def _norm(v) -> str:
    return (v or "").strip().lower().replace(" ", "")


def check_payee(supplier, inv: dict) -> list[Finding]:
    """Payment details printed on the invoice must match what we saved. We always pay the saved ones; a different
    UPI ID or account on the invoice is the classic 'changed bank details' fraud."""
    changed = []
    if inv.get("payee_upi") and _norm(inv["payee_upi"]) != _norm(supplier["upi_id"]):
        changed.append(f"UPI ID {inv['payee_upi']}")
    if inv.get("payee_account") and _norm(inv["payee_account"]) != _norm(supplier["bank_account"]):
        changed.append(f"bank account {inv['payee_account']}")
    elif inv.get("payee_ifsc") and supplier["ifsc"] and _norm(inv["payee_ifsc"]) != _norm(supplier["ifsc"]):
        changed.append(f"IFSC {inv['payee_ifsc']}")
    if not changed:
        return []
    return [Finding("payee_changed", BLOCK, f"Payee changed: invoice asks for {' and '.join(changed)}, which "
                                            f"{'does' if len(changed) == 1 else 'do'} not match the saved payment "
                                            f"details for {supplier['name']}")]


def paid_today_paise(conn, today: str | None = None, business_id: int = 1) -> int:
    """Total paid on the given IST calendar day (default: today in India). paid_at is stored in UTC."""
    day = today or timeutil.today_ist().isoformat()
    row = conn.execute(
        "SELECT COALESCE(SUM(total_paise), 0) FROM invoices WHERE status = 'PAID' AND business_id = ? "
        "AND date(paid_at, '+330 minutes') = ?", (business_id, day)).fetchone()
    return row[0]


def check_limits(conn, inv: dict, today: str | None = None, business_id: int = 1) -> list[Finding]:
    out = []
    total = inv["total_paise"]
    if total > config.PER_PAYMENT_LIMIT_PAISE:
        out.append(Finding("over_payment_limit", HOLD,
                           f"{money(total)} is over the per-payment limit of {money(config.PER_PAYMENT_LIMIT_PAISE)}"))
    already = paid_today_paise(conn, today, business_id)
    if already + total > config.DAILY_LIMIT_PAISE:
        out.append(Finding("over_daily_limit", HOLD,
                           f"Paying this would bring today's total to {money(already + total)}, "
                           f"over the daily limit of {money(config.DAILY_LIMIT_PAISE)}"))
    return out


def gst_findings(report: list[gst.GstResult]) -> list[Finding]:
    return [Finding(r.code, r.severity, r.message) for r in report if not r.ok]


def run_checks_with_report(conn, inv: dict, exclude_id: int | None = None, today: str | None = None, business_id: int = 1):
    """Run every deterministic check. Returns (findings, gst_report). No findings = everything passed."""
    findings = check_extraction(inv)
    if any(f.code in ("missing_fields", "no_line_items", "bad_line_items") for f in findings):
        return findings, []  # cannot run the other checks without the basic fields
    supplier = get_supplier(conn, inv["supplier_name"], business_id)
    business = businesses.get(conn, business_id)
    findings += check_supplier(supplier, inv["supplier_name"])
    report = gst.run_gst_checks(inv, business["gstin"], supplier["gstin"] if supplier else None)
    findings += gst_findings(report)
    if supplier is None:
        return findings, report
    findings += check_duplicate(conn, inv, supplier["id"], exclude_id)
    findings += check_po(conn, inv, supplier["id"])
    if supplier["approved"]:
        findings += check_payee(supplier, inv)
    findings += check_limits(conn, inv, today, business_id)
    return findings, report


def run_checks(conn, inv: dict, exclude_id: int | None = None, today: str | None = None, business_id: int = 1) -> list[Finding]:
    return run_checks_with_report(conn, inv, exclude_id, today, business_id)[0]
