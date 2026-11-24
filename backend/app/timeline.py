"""Invoice timeline for the dashboard drawer: the invoice's journey as six steps, each with a pass/fail state and a
plain-English reason. Built from what the pipeline already stored (the invoice row and its audit log); nothing is
recomputed, so it shows what actually happened."""
import json

from . import checks, decide, payouts, pipeline, timeutil

_READ_CODES = {"missing_fields", "no_line_items", "bad_line_items", "extraction_failed"}


def _step(key, title, state, summary, details=None):
    """state: pass | warn (needs a person) | fail (blocks) | skipped | pending."""
    return {"key": key, "title": title, "state": state, "summary": summary, "details": details or []}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def build(conn, inv_id: int) -> dict | None:
    inv = pipeline.get_invoice(conn, inv_id)
    if inv is None:
        return None
    events = [dict(r) for r in conn.execute("SELECT * FROM audit_log WHERE invoice_id=? ORDER BY id", (inv_id,))]
    dec = next((e for e in events if e["event"] == "decision"), None)
    d = json.loads(dec["details"]) if dec and dec["details"] else {}
    findings = d.get("findings")
    ai, ai_error = d.get("ai_review"), d.get("ai_error")
    report = inv["gst_report"]
    gst_codes = {r["code"] for r in report}
    read_findings = [f for f in findings or [] if f["code"] in _READ_CODES]
    rule_findings = [f for f in findings or [] if f["code"] not in _READ_CODES and f["code"] not in gst_codes]

    def worst(items):
        return "fail" if any(i["severity"] == "BLOCK" for i in items) else "warn"

    # 1. Read
    if read_findings:
        read = _step("read", "Read invoice", "warn", "Could not be read reliably", [f["message"] for f in read_findings])
    elif inv["supplier_name"] and inv["total_paise"] is not None:
        read = _step("read", "Read invoice", "pass",
                     f"Read {_plural(len(inv['line_items']), 'line item')}, total {checks.money(inv['total_paise'])}",
                     [f"Supplier: {inv['supplier_name']}", f"Invoice {inv['invoice_number']} dated {inv['invoice_date']}"])
    else:
        read = _step("read", "Read invoice", "pending", "Waiting to be read")
    read_ok = read["state"] == "pass"

    # 2. GST
    bad = [r for r in report if not r["ok"]]
    if not report:
        gst_step = _step("gst", "GST checks", "skipped", "Did not run because the invoice could not be read")
    elif bad:
        gst_step = _step("gst", "GST checks", worst(bad), f"{len(bad)} of {len(report)} failed", [r["message"] for r in bad])
    else:
        gst_step = _step("gst", "GST checks", "pass", f"All {len(report)} passed", [r["label"] for r in report])

    # 3. Rules
    if not read_ok:
        rules = _step("rules", "Rule checks", "skipped", "Did not run because the invoice could not be read")
    elif rule_findings:
        rules = _step("rules", "Rule checks", worst(rule_findings), f"{_plural(len(rule_findings), 'problem')} found",
                      [f["message"] for f in rule_findings])
    elif findings is None:
        rules = _step("rules", "Rule checks", "pending", "Not run yet")
    else:
        rules = _step("rules", "Rule checks", "pass", "All passed",
                      ["Supplier approved", "Not a duplicate", "Matches the purchase order",
                       "Payee matches saved details", "Within payment limits"])

    # 4. AI review
    if ai:
        score = ai["risk_score"]
        state = "fail" if score >= decide.AI_BLOCK_RISK else "warn" if score >= decide.AI_HOLD_RISK else "pass"
        ai_step = _step("ai", "AI review", state, f"Risk score {score:.2f}" + (" (high)" if state == "fail" else ""),
                        ai.get("reasons") or ["No scam signals found"])
    elif ai_error:
        ai_step = _step("ai", "AI review", "warn", "Unavailable, so a person must decide", [ai_error])
    elif dec:
        ai_step = _step("ai", "AI review", "skipped", "Skipped: a rule had already blocked this invoice, so no AI call was spent")
    else:
        ai_step = _step("ai", "AI review", "pending", "Not run yet")

    # 5. Decision
    if inv["decision"]:
        label = {"AUTO_PAY": "Auto-pay", "HOLD": "On hold", "BLOCK": "Blocked"}[inv["decision"]]
        state = {"AUTO_PAY": "pass", "HOLD": "warn", "BLOCK": "fail"}[inv["decision"]]
        decision = _step("decision", "Decision", state, label)  # the reason is shown in the step that caused it
        for e in events:
            if e["event"] in ("owner_approved", "owner_rejected", "approval_refused", "correction_requested"):
                decision["details"].append(f"{timeutil.to_ist(e['created_at'])}: {e['reason']}")
    else:
        decision = _step("decision", "Decision", "pending", "Not decided yet")

    # 6. Payout
    failed = [e for e in events if e["event"] == "payout_failed"]
    if inv["payout_batch_id"]:
        payout = _step("payout", "Payout", "fail" if inv["payout_status"] == "FAILED" else "pass",
                       f"Paid by {inv['payout_method']} to {inv['payout_destination']} ({inv['payout_status'].lower()})",
                       [f"Payout id {inv['payout_batch_id']}", payouts.SANDBOX_LABEL])
    elif failed and inv["status"] == "HELD":
        payout = _step("payout", "Payout", "fail", "Payout failed, invoice is back on hold", [failed[-1]["reason"] or ""])
    elif inv["status"] == "HELD":
        payout = _step("payout", "Payout", "pending", "Waiting for your approval")
    elif inv["status"] in ("BLOCKED", "REJECTED"):
        payout = _step("payout", "Payout", "skipped", "Not paid")
    else:
        payout = _step("payout", "Payout", "pending", "Not paid yet")
    return {"invoice_id": inv_id, "steps": [read, gst_step, rules, ai_step, decision, payout]}
