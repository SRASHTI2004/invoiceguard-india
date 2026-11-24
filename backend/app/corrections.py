"""Draft an email asking a supplier for a corrected tax invoice. Plain code, no AI, nothing is sent: the draft is shown
to the owner (copy, or open in their mail app) and the request is recorded in the audit log."""
from urllib.parse import quote

from . import audit, config, pipeline
from .money import inr


def _date(iso: str | None) -> str:
    from datetime import date
    try:
        d = date.fromisoformat(iso or "")
        return f"{d.day} {d:%b %Y}"
    except ValueError:
        return iso or "(date missing)"


def draft(conn, inv_id: int) -> dict:
    """Build the email for an on-hold invoice with a GST problem, and log that it was requested."""
    inv = pipeline.get_invoice(conn, inv_id)
    if inv is None:
        raise pipeline.ActionError("Invoice not found")
    if inv["status"] != "HELD":
        raise pipeline.ActionError("A corrected invoice can only be requested for an invoice that is on hold")
    failed = pipeline.gst_failures(conn, inv)
    if not failed:
        raise pipeline.ActionError("This invoice has no GST problem to correct")
    supplier = conn.execute("SELECT * FROM suppliers WHERE id=?", (inv["supplier_id"],)).fetchone() if inv["supplier_id"] else None
    to = (supplier["email"] if supplier and supplier["email"] else "") or ""
    name = supplier["name"] if supplier else (inv["supplier_name"] or "supplier")

    lines = [f"Dear {name} accounts team,", "",
             f"We received tax invoice {inv['invoice_number']} dated {_date(inv['invoice_date'])} for "
             f"{inr(inv['total_paise'])}" + (f" against our purchase order {inv['po_number']}." if inv["po_number"] else "."),
             "", "We are unable to process payment because of the following GST " + ("issue:" if len(failed) == 1 else "issues:"), ""]
    lines += [f"{i}. {f['label']}: {f['message']}" for i, f in enumerate(failed, 1)]
    lines += ["", "Please issue a corrected tax invoice (and, where the original was already reported, a credit note or "
              "amendment for it) so that we can claim input tax credit on the correct amount. Please quote the original "
              "invoice number on the corrected one.", "",
              f"Our details for the corrected invoice: {config.BUYER_NAME}, GSTIN {config.BUYER_GSTIN}.", "",
              "We will release payment promptly once the corrected invoice is received.", "",
              "Regards,", f"Accounts Payable, {config.BUYER_NAME}"]
    subject = f"Request for corrected tax invoice: {inv['invoice_number']} ({_date(inv['invoice_date'])})"
    body = "\n".join(lines)
    issues = "; ".join(f["label"] for f in failed)
    audit.log(conn, inv_id, "correction_requested", None,
              f"Drafted a request to {name}{f' ({to})' if to else ''} for a corrected invoice. GST issue: {issues}. "
              "The email is a draft for the owner to send; the app does not send it.",
              {"to": to, "subject": subject, "body": body, "failed_checks": [f["code"] for f in failed]})
    return {"to": to, "subject": subject, "body": body, "issues": [f["label"] for f in failed],
            "mailto": f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}", "sent": False}
