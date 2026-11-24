"""CSV export of PAID invoices for an accountant to import into Tally (or open in Excel).

Columns: Date, Supplier, Supplier GSTIN, Invoice No, Taxable Value, CGST, SGST, IGST, Total, Payment Reference.
Dates are DD-MM-YYYY (invoice date); amounts are plain rupees with two decimals (no symbol, no thousands separators) so
they import cleanly. The file is UTF-8 with a byte-order mark so Excel reads it correctly.
"""
import csv
import io
from datetime import date

COLUMNS = ["Date", "Supplier", "Supplier GSTIN", "Invoice No", "Taxable Value", "CGST", "SGST", "IGST", "Total",
           "Payment Reference"]
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe(text) -> str:
    """Supplier names and invoice numbers come from uploaded PDFs, so they are untrusted. A cell that starts with
    = + - @ would run as a formula when opened in Excel (CSV injection): prefix it with an apostrophe."""
    t = "" if text is None else str(text).replace("\r", " ").replace("\n", " ").strip()
    return "'" + t if t.startswith(_FORMULA_STARTS) else t


def rupees(paise) -> str:
    return "" if paise is None else f"{int(paise) / 100:.2f}"


def dmy(iso: str | None) -> str:
    try:
        d = date.fromisoformat(iso or "")
        return f"{d.day:02d}-{d.month:02d}-{d.year}"
    except ValueError:
        return iso or ""


def tally_csv(conn) -> str:
    """All paid invoices, oldest invoice date first. The supplier name and GSTIN are the SAVED, verified ones (the
    invoice's own text can be upper-cased, wrapped or tampered with), falling back to the extracted text if unlinked."""
    rows = conn.execute(
        "SELECT i.invoice_date, COALESCE(s.name, i.supplier_name) AS supplier_name, "
        "COALESCE(s.gstin, i.supplier_gstin) AS supplier_gstin, i.invoice_number, i.taxable_paise, i.cgst_paise, "
        "i.sgst_paise, i.igst_paise, i.total_paise, i.payout_batch_id "
        "FROM invoices i LEFT JOIN suppliers s ON s.id = i.supplier_id "
        "WHERE i.status = 'PAID' ORDER BY i.invoice_date, i.id").fetchall()
    out = io.StringIO(newline="")
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(COLUMNS)
    for r in rows:
        w.writerow([dmy(r["invoice_date"]), safe(r["supplier_name"]), safe(r["supplier_gstin"]), safe(r["invoice_number"]),
                    rupees(r["taxable_paise"]), rupees(r["cgst_paise"] or 0), rupees(r["sgst_paise"] or 0),
                    rupees(r["igst_paise"] or 0), rupees(r["total_paise"]), safe(r["payout_batch_id"])])
    return out.getvalue()
