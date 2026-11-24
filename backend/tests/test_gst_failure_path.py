import pytest
from fastapi.testclient import TestClient

from app import corrections, pipeline
from app.main import app
from tests.test_pipeline import run


def audit_rows(conn, event):
    return [dict(r) for r in conn.execute("SELECT * FROM audit_log WHERE event=? ORDER BY id", (event,))]


# ---- approve with a reason when GST failed ---------------------------------------------------------------------
def test_approving_a_gst_failure_needs_a_reason(env):
    conn, sent = env
    inv = run(conn, "inv08_pinnacle_wrong_tax_type.pdf")
    for bad in (None, "", "   ", "ok", "short"):
        with pytest.raises(pipeline.ActionError, match="GST problem"):
            pipeline.approve(conn, inv["id"], gst_reason=bad)
    assert sent == [] and pipeline.get_invoice(conn, inv["id"])["status"] == "HELD"


def test_reason_is_saved_in_the_audit_log_and_the_invoice_is_paid(env):
    conn, sent = env
    inv = run(conn, "inv08_pinnacle_wrong_tax_type.pdf")
    paid = pipeline.approve(conn, inv["id"], gst_reason="  Supplier   confirmed by phone; credit note to follow  ")
    assert paid["status"] == "PAID" and len(sent) == 1
    row = audit_rows(conn, "owner_approved")[0]
    assert "Approved despite a GST problem" in row["reason"] and "CGST+SGST vs IGST" in row["reason"]
    assert "Supplier confirmed by phone; credit note to follow" in row["reason"]  # whitespace tidied
    assert '"gst_override": true' in row["details"] and "wrong_tax_type" in row["details"]


def test_reason_is_capped(env):
    conn, _ = env
    inv = run(conn, "inv10_orchard_wrong_gst_total.pdf")
    pipeline.approve(conn, inv["id"], gst_reason="x" * 1000)
    assert len(audit_rows(conn, "owner_approved")[0]["details"]) < 900


def test_no_reason_needed_without_a_gst_problem(env):
    conn, _ = env
    conn.execute("DELETE FROM gemini_cache WHERE kind='review'")
    conn.commit()
    held = run(conn, "inv02_brightline.pdf")  # held only because the AI review is unavailable
    assert pipeline.approve(conn, held["id"])["status"] == "PAID"


def test_a_block_level_gst_failure_still_cannot_be_approved_with_any_reason(env):
    conn, sent = env
    inv = run(conn, "inv07_atlas_fake_gstin.pdf")  # BLOCKED: fake GSTIN
    with pytest.raises(pipeline.ActionError):
        pipeline.approve(conn, inv["id"], gst_reason="I really want to pay this one")
    assert sent == []


def test_approve_endpoint_requires_the_reason(env):
    conn, sent = env
    inv = run(conn, "inv08_pinnacle_wrong_tax_type.pdf")
    with TestClient(app) as c:
        r = c.post(f"/api/invoices/{inv['id']}/approve")
        assert r.status_code == 400 and "reason" in r.json()["detail"].lower()
        r = c.post(f"/api/invoices/{inv['id']}/approve", json={"reason": "Checked with the supplier today"})
        assert r.status_code == 200 and r.json()["status"] == "PAID"


def test_agent_cannot_confirm_a_gst_failure(env):
    conn, sent = env
    inv = run(conn, "inv08_pinnacle_wrong_tax_type.pdf")
    assert pipeline.confirm_proposal(conn, inv["id"])["paid"] is False and sent == []


# ---- corrected-invoice request ---------------------------------------------------------------------------------
def test_correction_draft_names_the_exact_gst_issue_and_is_logged(env):
    conn, _ = env
    inv = run(conn, "inv08_pinnacle_wrong_tax_type.pdf")
    d = corrections.draft(conn, inv["id"])
    assert d["to"] == "accounts@pinnacleprint.example.com" and d["sent"] is False
    assert "PP/2217" in d["subject"] and "3 Nov 2026" in d["subject"]
    assert "Wrong tax type" in d["body"] and "Tamil Nadu" in d["body"] and "IGST applies" in d["body"]
    assert "₹1,43,700.00" in d["body"] and "PO-2007" in d["body"] and "29AABCB5521M1ZJ" in d["body"]
    assert d["mailto"].startswith("mailto:accounts%40pinnacleprint.example.com?subject=")
    row = audit_rows(conn, "correction_requested")[0]
    assert row["invoice_id"] == inv["id"] and "CGST+SGST vs IGST" in row["reason"] and "does not send" in row["reason"]
    assert pipeline.get_invoice(conn, inv["id"])["status"] == "HELD"  # still on hold, nothing paid


def test_correction_draft_lists_every_failed_check(env):
    conn, _ = env
    inv = run(conn, "inv10_orchard_wrong_gst_total.pdf")
    body = corrections.draft(conn, inv["id"])["body"]
    assert "Invoice total" in body and "₹81,900.00" in body and "issue:" in body


def test_correction_only_for_held_invoices_with_a_gst_problem(env):
    conn, _ = env
    with pytest.raises(pipeline.ActionError, match="no GST problem"):
        conn.execute("DELETE FROM gemini_cache WHERE kind='review'"); conn.commit()
        corrections.draft(conn, run(conn, "inv02_brightline.pdf")["id"])  # held, but GST is fine
    with pytest.raises(pipeline.ActionError, match="on hold"):
        corrections.draft(conn, run(conn, "inv07_atlas_fake_gstin.pdf")["id"])  # blocked
    with pytest.raises(pipeline.ActionError, match="not found"):
        corrections.draft(conn, 9999)


def test_correction_endpoint_and_timeline(env):
    conn, _ = env
    inv = run(conn, "inv08_pinnacle_wrong_tax_type.pdf")
    with TestClient(app) as c:
        r = c.post(f"/api/invoices/{inv['id']}/request-correction")
        assert r.status_code == 200 and r.json()["issues"] == ["CGST+SGST vs IGST"]
        t = c.get(f"/api/invoices/{inv['id']}/timeline").json()
        decision = [s for s in t["steps"] if s["key"] == "decision"][0]
        assert any("corrected invoice" in d.lower() for d in decision["details"]) and any("IST" in d for d in decision["details"])
        assert c.post("/api/invoices/9999/request-correction").status_code == 400
