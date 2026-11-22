from fastapi.testclient import TestClient

from app import config, pipeline, timeline
from app.main import app
from tests.test_pipeline import run


def steps(conn, inv_id):
    return {s["key"]: s for s in timeline.build(conn, inv_id)["steps"]}


def test_valid_invoice_passes_every_step_and_shows_the_payout(env):
    conn, _ = env
    s = steps(conn, run(conn, "inv01_mahalaxmi.pdf")["id"])
    assert list(s) == ["read", "gst", "rules", "ai", "decision", "payout"]
    assert all(x["state"] == "pass" for x in s.values())
    assert "IMPS" in s["payout"]["summary"] and "SIMULATED" in s["payout"]["details"][1]


def test_wrong_tax_type_fails_at_gst_and_needs_a_person(env):
    conn, _ = env
    s = steps(conn, run(conn, "inv08_pinnacle_wrong_tax_type.pdf")["id"])
    assert s["gst"]["state"] == "warn" and "Wrong tax type" in s["gst"]["details"][0]
    assert s["rules"]["state"] == "pass" and s["decision"]["state"] == "warn"
    assert s["payout"]["state"] == "pending"


def test_fake_gstin_blocks_and_skips_the_ai_call(env):
    conn, _ = env
    s = steps(conn, run(conn, "inv07_atlas_fake_gstin.pdf")["id"])
    assert s["gst"]["state"] == "fail" and s["decision"]["state"] == "fail"
    assert s["ai"]["state"] == "skipped" and s["payout"]["state"] == "skipped"


def test_duplicate_and_changed_payee_fail_at_rules(env):
    conn, _ = env
    run(conn, "inv01_mahalaxmi.pdf")
    dup = steps(conn, run(conn, "inv06_mahalaxmi_duplicate.pdf")["id"])
    assert dup["rules"]["state"] == "fail" and "Duplicate" in dup["rules"]["details"][0] and dup["gst"]["state"] == "pass"
    payee = steps(conn, run(conn, "inv11_lumen_changed_payee.pdf")["id"])
    assert payee["rules"]["state"] == "fail" and "Payee changed" in payee["rules"]["details"][0]


def test_prompt_injection_fails_at_the_ai_review(env):
    conn, _ = env
    s = steps(conn, run(conn, "inv09_blueriver_injection.pdf")["id"])
    assert s["ai"]["state"] == "fail" and "high" in s["ai"]["summary"] and s["rules"]["state"] == "pass"


def test_unreadable_invoice_and_missing_ai(env):
    conn, _ = env
    s = steps(conn, pipeline.process_invoice(conn, b"%PDF-1.4 not in cache", "weird.pdf")["id"])
    assert s["read"]["state"] == "warn" and s["gst"]["state"] == "skipped" and s["rules"]["state"] == "skipped"
    conn.execute("DELETE FROM gemini_cache WHERE kind='review'")
    conn.commit()
    s = steps(conn, run(conn, "inv02_brightline.pdf")["id"])
    assert s["ai"]["state"] == "warn" and "Unavailable" in s["ai"]["summary"] and s["decision"]["state"] == "warn"


def test_payout_failure_and_owner_approval_appear(env, monkeypatch):
    conn, _ = env
    monkeypatch.setattr(config, "SANDBOX_BALANCE_PAISE", 100)
    inv = run(conn, "inv01_mahalaxmi.pdf")
    s = steps(conn, inv["id"])
    assert s["payout"]["state"] == "fail" and "insufficient funds" in s["payout"]["details"][0]
    monkeypatch.setattr(config, "SANDBOX_BALANCE_PAISE", 10**12)
    pipeline.approve(conn, inv["id"])
    s = steps(conn, inv["id"])
    assert s["payout"]["state"] == "pass" and any("Approved by the owner" in x for x in s["decision"]["details"])


def test_timeline_endpoint(env):
    conn, _ = env
    inv = run(conn, "inv01_mahalaxmi.pdf")
    with TestClient(app) as c:
        r = c.get(f"/api/invoices/{inv['id']}/timeline")
        assert r.status_code == 200 and len(r.json()["steps"]) == 6
        assert c.get("/api/invoices/999/timeline").status_code == 404
