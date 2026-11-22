"""End-to-end firewall tests on the real sample PDFs. Gemini results come from the pre-seeded cache
(the API key is blanked, so any real Gemini call would fail) and payouts go to the simulated sandbox."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config, payouts, pipeline
from app.main import app
from seed.data import DEMO_INVOICES, INVOICES, SUP, compute

SAMPLES = Path(__file__).parents[1] / "seed" / "invoices"
ALL = INVOICES + DEMO_INVOICES
BY_FILE = {i["file"]: i for i in ALL}
TOTAL = {i["file"]: compute(i)["total"] for i in ALL}
PAID_TOTAL = sum(TOTAL[i["file"]] for i in INVOICES if i["expected"] == "AUTO_PAY")
COUNTS = {"PAID": 5, "BLOCKED": 5, "HELD": 3}  # 5 valid, 5 blocked fraud, 2 held fraud + 1 partial delivery


def run(conn, filename):
    return pipeline.process_invoice(conn, (SAMPLES / filename).read_bytes(), filename)


def run_all(conn):
    return {i["file"]: run(conn, i["file"]) for i in ALL}  # in order: the duplicate comes after its original


def test_all_samples_get_the_expected_decision(env):
    conn, sent = env
    results = run_all(conn)
    for inv in INVOICES:
        r = results[inv["file"]]
        if inv["expected"] == "AUTO_PAY":
            assert r["decision"] == "AUTO_PAY" and r["status"] == "PAID", (inv["file"], r["reason"])
            assert r["payout_batch_id"].startswith("SIM-") and r["payout_status"] == "PENDING"
        elif inv["expected"] == "BLOCK":
            assert r["decision"] == "BLOCK" and r["status"] == "BLOCKED", (inv["file"], r["reason"])
        else:
            assert r["decision"] in ("HOLD", "BLOCK"), inv["file"]
        assert r["reason"]
    assert results["inv13_cedarpine_partial.pdf"]["status"] == "HELD"
    assert len(sent) == 5


def test_payouts_go_to_the_saved_destination_only(env):
    conn, sent = env
    run_all(conn)
    saved = {SUP[i["supplier"]]["upi"] for i in INVOICES} | {SUP[i["supplier"]]["account"] for i in INVOICES}
    for p in sent:
        d = p["destination"]
        assert (d.get("upi_id") or d.get("account")) in saved
    # the changed-payee invoice asked for a different UPI ID / account: nothing was ever sent there
    assert not any("lumen.accounts@ybl" in str(p["destination"]) or "918020099887766" in str(p["destination"]) for p in sent)
    assert {p["destination"]["method"] for p in sent} == {"UPI", "IMPS", "RTGS"}  # rails chosen by amount


def test_fraud_cases_have_the_right_reason(env):
    conn, _ = env
    r = run_all(conn)
    assert "Duplicate" in r["inv06_mahalaxmi_duplicate.pdf"]["reason"]
    assert "check character" in r["inv07_atlas_fake_gstin.pdf"]["reason"]
    assert "Wrong tax type" in r["inv08_pinnacle_wrong_tax_type.pdf"]["reason"]
    assert "AI review" in r["inv09_blueriver_injection.pdf"]["reason"]
    assert "total" in r["inv10_orchard_wrong_gst_total.pdf"]["reason"] and "wrong" in r["inv10_orchard_wrong_gst_total.pdf"]["reason"]
    assert "Payee changed" in r["inv11_lumen_changed_payee.pdf"]["reason"]
    assert "not on the approved list" in r["inv12_shadowline_unapproved.pdf"]["reason"]


def test_wrong_tax_type_and_wrong_total_are_held_for_a_person_not_paid(env):
    conn, sent = env
    for f in ("inv08_pinnacle_wrong_tax_type.pdf", "inv10_orchard_wrong_gst_total.pdf"):
        r = run(conn, f)
        assert r["status"] == "HELD" and r["decision"] == "HOLD"
    assert sent == []


def test_gst_report_is_stored_per_invoice(env):
    conn, _ = env
    good = run(conn, "inv01_mahalaxmi.pdf")
    assert good["gst_report"] and all(g["ok"] for g in good["gst_report"])
    assert {g["label"] for g in good["gst_report"]} >= {"Supplier GSTIN", "CGST+SGST vs IGST", "Invoice total"}
    bad = run(conn, "inv08_pinnacle_wrong_tax_type.pdf")
    failed = [g for g in bad["gst_report"] if not g["ok"]]
    assert [g["code"] for g in failed] == ["wrong_tax_type"] and failed[0]["severity"] == "HOLD"
    fake = run(conn, "inv07_atlas_fake_gstin.pdf")
    assert [g["code"] for g in fake["gst_report"] if not g["ok"]] == ["supplier_gstin_invalid"]


def test_gst_fields_are_extracted_and_saved_in_paise(env):
    conn, _ = env
    r = run(conn, "inv02_brightline.pdf")  # Karnataka -> Karnataka: CGST + SGST
    t = compute(BY_FILE["inv02_brightline.pdf"])
    assert (r["taxable_paise"], r["cgst_paise"], r["sgst_paise"], r["total_paise"]) == (
        t["taxable"], t["cgst"], t["sgst"], t["total"])
    assert not r["igst_paise"] and r["supplier_gstin"] == SUP[r["supplier_name"]]["gstin"]
    assert r["place_of_supply"].lower().startswith("29")


def test_every_decision_is_in_the_audit_log(env):
    conn, _ = env
    for inv in INVOICES[:6]:
        run(conn, inv["file"])
    n = conn.execute("SELECT COUNT(*) FROM audit_log WHERE event='decision'").fetchone()[0]
    assert n == 6


def test_unreadable_invoice_is_held_not_paid(env):
    conn, sent = env
    r = pipeline.process_invoice(conn, b"%PDF-1.4 not in cache", "weird.pdf")  # cache miss + no key -> Gemini error
    assert r["status"] == "HELD" and "manually" in r["reason"] and sent == []


def test_ai_failure_holds_instead_of_paying(env):
    conn, sent = env
    conn.execute("DELETE FROM gemini_cache WHERE kind='review'")
    conn.commit()
    r = run(conn, "inv02_brightline.pdf")  # extraction cached, review missing and Gemini unavailable
    assert r["status"] == "HELD" and "AI review unavailable" in r["reason"] and sent == []


def test_owner_can_approve_a_held_invoice_once_only(env):
    conn, sent = env
    conn.execute("DELETE FROM gemini_cache WHERE kind='review'")
    conn.commit()
    held = run(conn, "inv02_brightline.pdf")
    paid = pipeline.approve(conn, held["id"])
    assert paid["status"] == "PAID" and len(sent) == 1 and sent[0]["paise"] == TOTAL["inv02_brightline.pdf"]
    assert paid["payout_method"] == "IMPS" and paid["payout_destination"].endswith("2309")
    with pytest.raises(pipeline.ActionError):
        pipeline.approve(conn, held["id"])
    assert len(sent) == 1  # never paid twice


def test_payout_ref_makes_a_retry_idempotent(env):
    conn, sent = env
    r = run(conn, "inv01_mahalaxmi.pdf")
    ref = conn.execute("SELECT payout_ref FROM invoices WHERE id=?", (r["id"],)).fetchone()[0]
    assert ref and conn.execute("SELECT COUNT(*) FROM payouts WHERE ref=?", (ref,)).fetchone()[0] == 1
    # even if the status flag were lost and the payout re-sent with the same ref, the ledger holds one payout
    conn.execute("UPDATE invoices SET status='HELD' WHERE id=?", (r["id"],))
    conn.commit()
    again = pipeline.pay_invoice(conn, r["id"], actor="owner")
    assert again["payout_batch_id"] == r["payout_batch_id"]
    assert tuple(conn.execute("SELECT COUNT(*), SUM(amount_paise) FROM payouts").fetchone()) == (
        1, TOTAL["inv01_mahalaxmi.pdf"])


def test_blocked_invoice_cannot_be_approved(env):
    conn, sent = env
    blocked = run(conn, "inv12_shadowline_unapproved.pdf")
    with pytest.raises(pipeline.ActionError):
        pipeline.approve(conn, blocked["id"])
    assert sent == []


def test_reject_and_summary(env):
    conn, _ = env
    conn.execute("DELETE FROM gemini_cache WHERE kind='review'")
    conn.commit()
    held = run(conn, "inv02_brightline.pdf")
    run(conn, "inv12_shadowline_unapproved.pdf")
    assert pipeline.summary(conn)["total_held_paise"] == TOTAL["inv02_brightline.pdf"]
    assert pipeline.reject(conn, held["id"])["status"] == "REJECTED"
    s = pipeline.summary(conn)
    assert s["money_saved_paise"] == TOTAL["inv02_brightline.pdf"] + TOTAL["inv12_shadowline_unapproved.pdf"]
    assert s["total_paid_paise"] == 0


def test_payout_failure_returns_invoice_to_held(env, monkeypatch):
    conn, _ = env

    def boom(*a, **k):
        raise payouts.PayoutError("The bank rejected the beneficiary account", "BENEFICIARY_REJECTED")

    monkeypatch.setattr(payouts, "send_payout", boom)
    r = run(conn, "inv01_mahalaxmi.pdf")
    assert r["status"] == "HELD" and r["reason"].startswith("Payout failed: The bank rejected")
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE event='payout_failed'").fetchone()[0] == 1


def test_refresh_payout_status(env):
    conn, _ = env
    r = run(conn, "inv01_mahalaxmi.pdf")
    assert r["payout_status"] == "PENDING"
    assert pipeline.refresh_payout(conn, r["id"])["payout_status"] == "SUCCESS"
    with pytest.raises(pipeline.ActionError):
        pipeline.refresh_payout(conn, run(conn, "inv12_shadowline_unapproved.pdf")["id"])


def test_api_upload_list_summary(env):
    with TestClient(app) as client:
        pdf = (SAMPLES / "inv01_mahalaxmi.pdf").read_bytes()
        r = client.post("/api/invoices/upload", files={"file": ("a.pdf", pdf, "application/pdf")})
        assert r.status_code == 200 and r.json()["status"] == "PAID"
        assert client.post("/api/invoices/upload", files={"file": ("a.txt", b"hello", "text/plain")}).status_code == 400
        listed = client.get("/api/invoices").json()
        assert len(listed) == 1 and listed[0]["gst_report"] and listed[0]["payout_method"]
        assert client.get("/api/summary").json()["total_paid_paise"] == TOTAL["inv01_mahalaxmi.pdf"]
        suppliers = client.get("/api/suppliers").json()
        assert len(suppliers) == 12 and all("gstin" in s for s in suppliers)
        assert not any(s["bank_account"] and "50200034871265" in s["bank_account"] for s in suppliers)  # masked
        assert client.post("/api/invoices/999/approve").status_code == 400
        assert client.post("/api/demo/run-samples").json()["processed"] == 13  # resets first, then loads all 13
        assert len(client.get("/api/invoices").json()) == 13
        assert client.get("/api/audit").status_code == 200
        cfg = client.get("/api/config").json()
        assert cfg["currency"] == "INR" and "SIMULATED" in cfg["payout_label"]


def test_approve_rechecks_at_click_time(env):
    conn, sent = env
    conn.execute("DELETE FROM gemini_cache WHERE kind='review'")
    conn.commit()
    held = run(conn, "inv02_brightline.pdf")
    conn.execute("UPDATE suppliers SET bank_account='999900001111' WHERE name='Brightline Packaging Pvt Ltd'")
    conn.commit()
    with pytest.raises(pipeline.ActionError, match="checks now fail"):
        pipeline.approve(conn, held["id"])
    assert sent == []
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE event='approval_refused'").fetchone()[0] == 1


def snapshot(conn):
    rows = conn.execute("SELECT id, filename, status, decision, total_paise FROM invoices ORDER BY id").fetchall()
    return [tuple(r) for r in rows], pipeline.summary(conn)


def test_load_samples_gives_the_same_result_every_time(env):
    conn, sent = env
    with TestClient(app) as client:
        first = client.post("/api/demo/run-samples").json()
        a = snapshot(conn)
        second = client.post("/api/demo/run-samples").json()
        b = snapshot(conn)
    assert a == b and first["invoice_ids"] == second["invoice_ids"] == list(range(1, 14))  # ids restart at 1
    s = second["summary"]
    assert s["counts"] == COUNTS
    assert s["total_paid_paise"] == PAID_TOTAL
    assert len(sent) == 10  # 5 paid per run; nothing was skipped because of earlier runs
    assert conn.execute("SELECT COUNT(*) FROM payouts").fetchone()[0] == 5  # the ledger is reset too


def test_leftover_data_cannot_change_the_sample_result(env):
    conn, sent = env
    # Leftovers from earlier runs: a big payment made today (eats the daily limit) and a duplicate invoice number.
    conn.execute("INSERT INTO invoices (supplier_id, supplier_name, invoice_number, invoice_date, total_paise, "
                 "status, paid_at) VALUES (1, 'Mahalaxmi Office Supplies', 'MOS/26-27/1041', '2026-10-28', 140000000, "
                 "'PAID', datetime('now'))")
    conn.commit()
    with TestClient(app) as client:
        client.post("/api/demo/run-samples")
    s = pipeline.summary(conn)
    assert s["counts"] == COUNTS and s["total_paid_paise"] == PAID_TOTAL
    assert conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 13


def test_reset_keeps_suppliers_pos_and_gemini_cache(env):
    conn, _ = env
    run(conn, "inv01_mahalaxmi.pdf")
    n_cache = conn.execute("SELECT COUNT(*) FROM gemini_cache").fetchone()[0]
    pipeline.reset_demo_data(conn)
    assert conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM payouts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == 12
    assert conn.execute("SELECT COUNT(*) FROM gemini_cache").fetchone()[0] == n_cache


def test_insufficient_funds_holds_the_invoice_with_a_clear_reason(env, monkeypatch):
    conn, _ = env
    monkeypatch.setattr(config, "SANDBOX_BALANCE_PAISE", 100)  # wallet is empty
    r = run(conn, "inv01_mahalaxmi.pdf")
    assert r["status"] == "HELD" and r["reason"] == pipeline.INSUFFICIENT_FUNDS_MESSAGE
    assert "insufficient funds" in r["reason"] and "Top up" in r["reason"]
    audit = conn.execute("SELECT reason, details FROM audit_log WHERE event='payout_failed'").fetchone()
    assert audit["reason"] == pipeline.INSUFFICIENT_FUNDS_MESSAGE and "INSUFFICIENT_FUNDS" in audit["details"]
    # after the wallet is topped up, Approve works (same invoice, no loss)
    monkeypatch.setattr(config, "SANDBOX_BALANCE_PAISE", 10**12)
    assert pipeline.approve(conn, r["id"])["status"] == "PAID"


def test_beneficiary_rejection_holds_instead_of_paying(env, monkeypatch):
    conn, sent = env
    real = payouts.destination_for
    monkeypatch.setattr(payouts, "destination_for",
                        lambda sup, amt: {**real(sup, amt), "upi_id": "fail.me@okaxis", "account": "fail"})
    r = run(conn, "inv01_mahalaxmi.pdf")
    assert r["status"] == "HELD" and r["reason"].startswith("Payout failed: The bank rejected")
    assert sent == [] and conn.execute("SELECT COUNT(*) FROM payouts").fetchone()[0] == 0


def test_demo_reset_is_rate_limited_and_sends_no_extra_payouts(env, monkeypatch):
    conn, sent = env
    monkeypatch.setattr(config, "DEMO_COOLDOWN_SECONDS", 600)
    with TestClient(app) as client:
        first = client.post("/api/demo/run-samples").json()
        assert first["throttled"] is False and len(sent) == 5
        before = snapshot(conn)
        again = client.post("/api/demo/run-samples").json()
    assert again["throttled"] is True and "recently" in again["note"]
    assert len(sent) == 5 and snapshot(conn) == before  # nothing re-run, data untouched
    assert again["processed"] == 13 and again["summary"]["counts"] == COUNTS
