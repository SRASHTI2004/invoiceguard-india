"""The firewall pipeline: extract -> checks -> AI review -> decide -> pay/hold/block -> audit.

Only decide.py's output (or an explicit owner approval of a HELD invoice) can lead to a payment.
"""
import json
import secrets

from . import ai_review, audit, checks, decide, extract, gemini, payouts, timeutil


INSUFFICIENT_FUNDS_MESSAGE = (
    "Payment not sent: the payout wallet has insufficient funds. Top up the wallet, "
    "then click Approve to try again. The invoice passed all checks and nothing was lost.")


class ActionError(Exception):
    """A user-facing problem (wrong invoice state, cannot pay, ...)."""


def get_invoice(conn, invoice_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if row is None:
        return None
    inv = dict(row)
    inv["line_items"] = json.loads(inv["line_items"]) if inv["line_items"] else []
    inv["gst_report"] = json.loads(inv["gst_report"]) if inv["gst_report"] else []
    return inv


_SAVED_FIELDS = ("supplier_name", "supplier_gstin", "buyer_gstin", "place_of_supply", "invoice_number",
                 "invoice_date", "due_date", "po_number", "taxable_paise", "cgst_paise", "sgst_paise", "igst_paise",
                 "total_paise", "payee_upi", "payee_account", "payee_ifsc")


def _save_extraction(conn, inv_id: int, inv: dict) -> None:
    supplier = checks.get_supplier(conn, inv["supplier_name"]) if inv.get("supplier_name") else None
    sets = ", ".join(f"{f}=?" for f in _SAVED_FIELDS)
    conn.execute(f"UPDATE invoices SET supplier_id=?, line_items=?, {sets} WHERE id=?",
                 (supplier["id"] if supplier else None, json.dumps(inv["line_items"]),
                  *(inv[f] for f in _SAVED_FIELDS), inv_id))
    conn.commit()


def process_invoice(conn, pdf_bytes: bytes, filename: str, gemini_client=None, accepted_date: str | None = None) -> dict:
    """Run one uploaded invoice through the whole firewall and return the saved invoice.
    accepted_date (IST, YYYY-MM-DD) is when we accepted it: the MSME payment clock starts there. Default: today."""
    cur = conn.execute("INSERT INTO invoices (filename, file_hash, status, accepted_date) VALUES (?, ?, 'RECEIVED', ?)",
                       (filename, gemini.pdf_hash(pdf_bytes), accepted_date or timeutil.today_ist().isoformat()))
    conn.commit()
    inv_id = cur.lastrowid
    audit.log(conn, inv_id, "received", details={"filename": filename})

    inv = None
    try:
        inv = extract.extract_invoice(pdf_bytes, conn, gemini_client)
        _save_extraction(conn, inv_id, inv)
        findings, report = checks.run_checks_with_report(conn, inv, exclude_id=inv_id)
        conn.execute("UPDATE invoices SET gst_report=? WHERE id=?",
                     (json.dumps([r.as_dict() for r in report]), inv_id))
        conn.commit()
    except gemini.GeminiError as e:
        findings = [checks.Finding("extraction_failed", checks.HOLD,
                                   f"Could not read the invoice automatically ({e}); please review it manually")]

    ai, ai_error = None, None
    if inv and not any(f.severity == checks.BLOCK for f in findings):  # already blocked: save the Gemini call
        try:
            ai = ai_review.review_invoice(pdf_bytes, conn, gemini_client)
        except gemini.GeminiError as e:
            ai_error = str(e)

    d = decide.decide(findings, ai)
    status = {"AUTO_PAY": "RECEIVED", "HOLD": "HELD", "BLOCK": "BLOCKED"}[d.decision]
    conn.execute("UPDATE invoices SET decision=?, reason=?, risk_score=?, status=? WHERE id=?",
                 (d.decision, d.reason, d.risk_score, status, inv_id))
    conn.commit()
    audit.log(conn, inv_id, "decision", d.decision, d.reason, {
        "findings": [f.__dict__ for f in findings], "ai_review": ai, "ai_error": ai_error})

    if d.decision == decide.AUTO_PAY:
        try:
            pay_invoice(conn, inv_id, actor="auto")
        except ActionError:
            pass  # the invoice is back on HOLD with the reason (already saved and audited)
    return get_invoice(conn, inv_id)


def pay_invoice(conn, inv_id: int, actor: str) -> dict:
    """Pay an invoice. The payee is ALWAYS the supplier's saved UPI ID / bank account, never what the invoice says."""
    # Atomic claim so a double click / retry can never pay twice.
    claimed = conn.execute("UPDATE invoices SET status='PAYING' WHERE id=? AND status IN ('HELD','RECEIVED')",
                           (inv_id,)).rowcount
    conn.commit()
    if not claimed:
        raise ActionError("This invoice is not waiting for payment")
    inv = get_invoice(conn, inv_id)
    supplier = conn.execute("SELECT * FROM suppliers WHERE id=?", (inv["supplier_id"],)).fetchone()         if inv["supplier_id"] else None
    if supplier is None or not supplier["approved"] or not inv["total_paise"]:
        _back_to_held(conn, inv_id, "Cannot pay: supplier or amount is missing or not approved")
        raise ActionError("Cannot pay this invoice: supplier or amount is missing or not approved")

    ref = inv["payout_ref"] or f"ig-{inv_id}-{secrets.token_hex(4)}"  # idempotency key for the payout
    conn.execute("UPDATE invoices SET payout_ref=? WHERE id=?", (ref, inv_id))
    conn.commit()
    try:
        dest = payouts.destination_for(supplier, inv["total_paise"])
        res = payouts.send_payout(conn, ref, dest, inv["total_paise"],
                                  f"Invoice {inv['invoice_number']} from {supplier['name']}")
    except payouts.PayoutError as e:
        message = INSUFFICIENT_FUNDS_MESSAGE if e.code == "INSUFFICIENT_FUNDS" else f"Payout failed: {e}"
        _back_to_held(conn, inv_id, message)
        audit.log(conn, inv_id, "payout_failed", "HOLD", message, {"actor": actor, "payout_error": str(e), "code": e.code})
        raise ActionError(message)
    conn.execute("UPDATE invoices SET status='PAID', payout_batch_id=?, payout_status=?, payout_method=?, "
                 "payout_destination=?, paid_at=datetime('now') WHERE id=?",
                 (res["batch_id"], res["status"], res["method"], res["destination"], inv_id))
    conn.commit()
    audit.log(conn, inv_id, "paid", "AUTO_PAY" if actor == "auto" else "APPROVED",
              f"Paid {checks.money(inv['total_paise'])} to {supplier['name']} by {res['method']} "
              f"({res['destination']}) [{payouts.SANDBOX_LABEL}]",
              {"actor": actor, "payout_id": res["batch_id"], "payout_status": res["status"], "method": res["method"]})
    return get_invoice(conn, inv_id)


def _back_to_held(conn, inv_id: int, reason: str) -> None:
    conn.execute("UPDATE invoices SET status='HELD', decision='HOLD', reason=? WHERE id=?", (reason, inv_id))
    conn.commit()


MIN_REASON_CHARS = 8
MAX_REASON_CHARS = 300


def gst_failures(conn, inv: dict) -> list[dict]:
    """Fresh GST check at this moment: the failed results (empty = no GST problem)."""
    if not inv["supplier_name"] or inv["total_paise"] is None:
        return []
    _, report = checks.run_checks_with_report(conn, _check_input(inv), exclude_id=inv["id"])
    return [r.as_dict() for r in report if not r.ok]


def approve(conn, inv_id: int, note: str | None = None, gst_reason: str | None = None) -> dict:
    """Owner approval of a HELD invoice. Re-runs the checks first. If the invoice still has a GST problem the owner
    must give a short reason, which is saved in the audit log."""
    inv = get_invoice(conn, inv_id)
    if inv is None:
        raise ActionError("Invoice not found")
    if inv["status"] != "HELD":
        raise ActionError("Only invoices on hold can be approved")
    blockers = hard_blockers(conn, inv)  # re-run the checks at the moment of approval
    if blockers:
        audit.log(conn, inv_id, "approval_refused", "BLOCK", "; ".join(blockers))
        raise ActionError("Cannot approve, the checks now fail: " + "; ".join(blockers))
    failed = gst_failures(conn, inv)
    if failed:
        reason = " ".join((gst_reason or "").split())
        if len(reason) < MIN_REASON_CHARS:
            raise ActionError(f"This invoice has a GST problem ({', '.join(f['label'] for f in failed)}). "
                              f"Enter a short reason (at least {MIN_REASON_CHARS} characters) to approve it anyway.")
        reason = reason[:MAX_REASON_CHARS]
        audit.log(conn, inv_id, "owner_approved", "APPROVED",
                  f"Approved despite a GST problem ({', '.join(f['label'] for f in failed)}). Reason given: {reason}",
                  {"gst_override": True, "reason": reason, "failed_checks": [f["code"] for f in failed]})
    else:
        audit.log(conn, inv_id, "owner_approved", "APPROVED", note or "Approved by the owner")
    return pay_invoice(conn, inv_id, actor="owner")


def _check_input(inv: dict) -> dict:
    return {k: inv[k] for k in ("line_items",) + _SAVED_FIELDS}


def hard_blockers(conn, inv: dict) -> list[str]:
    """Fresh deterministic re-check: messages of any BLOCK-level finding (duplicate, PO, payee email, supplier)."""
    if not inv["supplier_name"] or inv["total_paise"] is None:
        return []  # unreadable invoice: pay_invoice refuses it
    fresh = checks.run_checks(conn, _check_input(inv), exclude_id=inv["id"])
    return [f.message for f in fresh if f.severity == checks.BLOCK]


def reject(conn, inv_id: int) -> dict:
    inv = get_invoice(conn, inv_id)
    if inv is None:
        raise ActionError("Invoice not found")
    changed = conn.execute("UPDATE invoices SET status='REJECTED' WHERE id=? AND status='HELD'", (inv_id,)).rowcount
    conn.commit()
    if not changed:
        raise ActionError("Only invoices on hold can be rejected")
    audit.log(conn, inv_id, "owner_rejected", "REJECTED", "Rejected by the owner")
    return get_invoice(conn, inv_id)


def refresh_payout(conn, inv_id: int) -> dict:
    inv = get_invoice(conn, inv_id)
    if inv is None or not inv["payout_batch_id"]:
        raise ActionError("This invoice has no payout to refresh")
    try:
        status = payouts.get_payout_status(conn, inv["payout_batch_id"])
    except payouts.PayoutError as e:
        raise ActionError(str(e))
    conn.execute("UPDATE invoices SET payout_status=? WHERE id=?", (status, inv_id))
    conn.commit()
    if status != inv["payout_status"]:
        audit.log(conn, inv_id, "payout_status", None, f"Payout status is now {status}",
                  {"payout_batch_id": inv["payout_batch_id"]})
    return get_invoice(conn, inv_id)


def reset_demo_data(conn) -> None:
    """Wipe invoices, payouts and the audit log (keeps suppliers, POs and the Gemini cache) and restart the ids at 1,
    so the sample run gives the same result every time (no leftover duplicates, daily-limit totals or ids)."""
    conn.execute("DELETE FROM audit_log")
    conn.execute("DELETE FROM invoices")
    conn.execute("DELETE FROM payouts")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('invoices', 'audit_log')")
    conn.commit()


def itc_summary(conn) -> dict:
    """Input tax credit (ITC) at stake. 'Protected' = the GST amount on blocked or rejected invoices that failed a GST
    check (invalid GSTIN, wrong tax type or arithmetic): paying them would have put the buyer's ITC at risk.
    'At risk' = the same for invoices still on hold, until a person decides."""
    out = {"itc_protected_paise": 0, "itc_protected_count": 0, "itc_at_risk_paise": 0, "itc_at_risk_count": 0}
    for r in conn.execute("SELECT status, cgst_paise, sgst_paise, igst_paise, gst_report FROM invoices "
                          "WHERE status IN ('BLOCKED','REJECTED','HELD') AND gst_report IS NOT NULL"):
        if not any(not c["ok"] for c in json.loads(r["gst_report"])):
            continue
        gst = (r["cgst_paise"] or 0) + (r["sgst_paise"] or 0) + (r["igst_paise"] or 0)
        key = "itc_at_risk" if r["status"] == "HELD" else "itc_protected"
        out[f"{key}_paise"] += gst
        out[f"{key}_count"] += 1
    return out


def summary(conn) -> dict:
    def total(where):
        return conn.execute(f"SELECT COALESCE(SUM(total_paise),0) FROM invoices WHERE {where}").fetchone()[0]
    counts = {r["status"]: r["n"] for r in conn.execute("SELECT status, COUNT(*) n FROM invoices GROUP BY status")}
    return {
        "total_paid_paise": total("status='PAID'"),
        "total_blocked_paise": total("status='BLOCKED'"),
        "total_held_paise": total("status='HELD'"),
        "money_saved_paise": total("status IN ('BLOCKED','REJECTED')"),
        "counts": counts,
        "invoice_count": sum(counts.values()),
        **itc_summary(conn),
    }


# ---- AP agent support -------------------------------------------------------------------------------------------
# The agent can only RECOMMEND. Money moves only when the owner confirms, through approve() above.
# The agent may recommend only these SOFT holds; everything else needs the owner's own judgement on Approvals.
AGENT_ALLOWED_FINDINGS = {"under_po", "no_po"}


def proposal_refusals(conn, inv: dict) -> list[str]:
    """Why this invoice must NOT be recommended / confirmed through the agent (empty = fine). Fresh re-check."""
    if inv["status"] != "HELD":
        return [f"Invoice is {inv['status']}; only invoices on hold can be proposed"]
    if not inv["supplier_name"] or inv["total_paise"] is None:
        return ["Invoice could not be read properly; the owner must review it"]
    fresh = checks.run_checks(conn, _check_input(inv), exclude_id=inv["id"])
    out = [f.message for f in fresh if f.code not in AGENT_ALLOWED_FINDINGS]
    if inv["risk_score"] is None or inv["risk_score"] >= decide.AI_HOLD_RISK:
        out.append("AI review risk is missing or not low; the owner must review this one")
    return out


def propose_payment(conn, inv_id: int) -> dict:
    """Read-only for money: re-runs the checks and returns a recommendation. Never pays."""
    inv = get_invoice(conn, inv_id)
    if inv is None:
        return {"invoice_id": inv_id, "recommended": False, "reasons": ["Invoice not found"]}
    refusals = proposal_refusals(conn, inv)
    if refusals:
        audit.log(conn, inv_id, "agent_proposal", "NOT_RECOMMENDED", "; ".join(refusals))
        return {"invoice_id": inv_id, "recommended": False, "reasons": refusals}
    reasons = [f"On hold only because: {inv['reason']}",
               "Fresh checks found no fraud signals or limit problems and the AI review risk is low"]
    audit.log(conn, inv_id, "agent_proposal", "RECOMMENDED", "; ".join(reasons))
    return {"invoice_id": inv_id, "recommended": True, "reasons": reasons}


def confirm_proposal(conn, inv_id: int) -> dict:
    """The owner clicked "Confirm and pay". Re-check everything now, then pay via the normal approve path."""
    inv = get_invoice(conn, inv_id)
    if inv is None:
        return {"invoice_id": inv_id, "paid": False, "message": "Invoice not found"}
    refusals = proposal_refusals(conn, inv)
    if refusals:
        audit.log(conn, inv_id, "agent_confirm_refused", None, "; ".join(refusals))
        return {"invoice_id": inv_id, "paid": False, "message": "Not paid: " + "; ".join(refusals)}
    try:
        paid = approve(conn, inv_id, note="Approved by the owner by confirming an AP agent proposal")
    except ActionError as e:
        return {"invoice_id": inv_id, "paid": False, "message": str(e)}
    return {"invoice_id": inv_id, "paid": True, "message": f"Paid {checks.money(paid['total_paise'])}",
            "payout_status": paid["payout_status"]}
