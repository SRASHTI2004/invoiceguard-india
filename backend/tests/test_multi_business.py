"""One login, several client businesses (a CA firm). Each business has its own GSTIN, suppliers, invoices, summary,
audit trail, export and agent view, and nothing leaks between them."""
import csv
import io
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import agent, businesses, checks, config, corrections, db, pipeline
from app.main import app
from seed.data import BUSINESSES, DEMO_RUNS, INVOICES2, SUP
from tests.test_checks import good_invoice

H1, H2 = {"X-Business-Id": "1"}, {"X-Business-Id": "2"}
SEED = Path(__file__).parents[1] / "seed"


@pytest.fixture()
def demo(env):
    """The full demo loaded through the API (both businesses)."""
    conn, sent = env
    with TestClient(app) as c:
        c.post("/api/demo/run-samples")
        yield c, conn, sent


def process(conn, folder, name, business_id):
    return pipeline.process_invoice(conn, (SEED / folder / name).read_bytes(), name, business_id=business_id)


# ---- the businesses --------------------------------------------------------------------------------------------
def test_two_businesses_with_valid_distinct_gstins(demo):
    c, conn, _ = demo
    listed = c.get("/api/businesses").json()
    assert [b["short_name"] for b in listed] == ["Bluebird Retail", "Kaveri Textiles"]
    assert listed[0]["gstin"] != listed[1]["gstin"] and listed[0]["gstin"][:2] == "29" and listed[1]["gstin"][:2] == "33"
    assert (listed[0]["invoice_count"], listed[1]["invoice_count"]) == (13, 7)
    assert (listed[0]["held_count"], listed[1]["held_count"]) == (3, 2)
    from app.gst import validate_gstin
    assert all(validate_gstin(b["gstin"])[0] for b in listed)


def test_default_is_business_one_and_bad_ids_are_rejected(demo):
    c, *_ = demo
    assert c.get("/api/config").json()["business_id"] == 1
    assert c.get("/api/config", headers=H2).json()["buyer_name"] == "Kaveri Textiles Pvt Ltd"
    assert c.get("/api/config?business=2").json()["business_id"] == 2  # the query form works too
    assert c.get("/api/config", headers={"X-Business-Id": "9"}).status_code == 404
    assert c.get("/api/config", headers={"X-Business-Id": "abc"}).status_code == 400


# ---- isolation ------------------------------------------------------------------------------------------------
def test_each_business_sees_only_its_own_data(demo):
    c, *_ = demo
    a, b = c.get("/api/invoices", headers=H1).json(), c.get("/api/invoices", headers=H2).json()
    assert (len(a), len(b)) == (13, 7)
    assert not {i["id"] for i in a} & {i["id"] for i in b}
    sa, sb = c.get("/api/suppliers", headers=H1).json(), c.get("/api/suppliers", headers=H2).json()
    assert (len(sa), len(sb)) == (12, 5) and not {s["name"] for s in sa} & {s["name"] for s in sb}


def test_summary_and_itc_are_per_business(demo):
    c, *_ = demo
    s1, s2 = c.get("/api/summary", headers=H1).json(), c.get("/api/summary", headers=H2).json()
    assert s1["counts"] == {"PAID": 5, "BLOCKED": 5, "HELD": 3}
    assert s2["counts"] == {"PAID": 3, "BLOCKED": 2, "HELD": 2}
    assert (s1["itc_protected_paise"], s1["itc_at_risk_paise"]) == (4658000, 2010000)
    assert (s2["itc_protected_paise"], s2["itc_at_risk_paise"]) == (0, 300000)  # only the Tirupur wrong-tax-type invoice


def test_other_businesses_invoices_do_not_exist_for_you(demo):
    c, conn, sent = demo
    mine = [i for i in c.get("/api/invoices", headers=H1).json() if i["status"] == "PAID"][0]["id"]  # paid: nothing to act on
    theirs = c.get("/api/invoices", headers=H2).json()[0]["id"]
    before = len(sent)
    for method, path in (("get", ""), ("get", "/timeline"), ("post", "/approve"), ("post", "/reject"),
                         ("post", "/request-correction"), ("post", "/refresh-payout")):
        r = getattr(c, method)(f"/api/invoices/{theirs}{path}", headers=H1)
        assert r.status_code == 404, (method, path, r.status_code)
        assert getattr(c, method)(f"/api/invoices/{mine}{path}", headers=H1).status_code != 404, path
    assert len(sent) == before
    assert c.post("/api/invoices/9999/approve", headers=H1).status_code == 400  # a missing id behaves as before


def test_audit_log_is_per_business(demo):
    c, conn, _ = demo
    ids1 = {i["id"] for i in c.get("/api/invoices", headers=H1).json()}
    rows2 = c.get("/api/audit", headers=H2).json()
    assert rows2 and not {r["invoice_id"] for r in rows2} & ids1
    assert all(r["invoice_id"] in ids1 for r in c.get("/api/audit", headers=H1).json())
    one_of_theirs = rows2[0]["invoice_id"]
    assert c.get(f"/api/audit?invoice_id={one_of_theirs}", headers=H1).json() == []


def test_a_supplier_of_another_business_is_unknown(env):
    conn, sent = env
    # Kaveri's supplier invoice uploaded into Bluebird: not one of Bluebird's suppliers
    r = process(conn, "invoices", INVOICES2[0]["file"], 1)
    assert r["status"] == "BLOCKED" and "not a known supplier" in r["reason"] and sent == []
    # the same invoice in its own business is fine
    ok = process(conn, "invoices", INVOICES2[0]["file"], 2)
    assert ok["status"] == "PAID" and ok["business_id"] == 2
    # and Bluebird's supplier invoice uploaded into Kaveri is unknown there
    assert "not a known supplier" in process(conn, "invoices", "inv01_mahalaxmi.pdf", 2)["reason"]


def test_invoices_must_be_billed_to_the_businesss_own_gstin(env):
    conn, _ = env
    findings, report = checks.run_checks_with_report(conn, good_invoice(), business_id=2)  # Bluebird invoice, Kaveri context
    assert "buyer_gstin_mismatch" in {f.code for f in findings}
    assert not [r for r in report if r.code == "buyer_gstin_mismatch"][0].ok
    findings, _ = checks.run_checks_with_report(conn, good_invoice(), business_id=1)
    assert findings == []


def test_duplicate_and_daily_limit_do_not_cross_businesses(env):
    conn, _ = env
    process(conn, "invoices", "inv01_mahalaxmi.pdf", 1)
    assert checks.paid_today_paise(conn, business_id=1) > 0 and checks.paid_today_paise(conn, business_id=2) == 0
    process(conn, "invoices", INVOICES2[0]["file"], 2)
    assert checks.paid_today_paise(conn, business_id=2) > 0
    # same invoice number in the other business is not a duplicate (different supplier, different business)
    findings = checks.run_checks(conn, good_invoice(invoice_number="CCM/26-27/2210"), business_id=1)
    assert "duplicate_number" not in {f.code for f in findings}


def test_tally_export_is_per_business(demo):
    c, *_ = demo
    r1, r2 = c.get("/api/export/tally.csv", headers=H1), c.get("/api/export/tally.csv", headers=H2)
    assert "bluebird-retail" in r1.headers["content-disposition"] and "kaveri-textiles" in r2.headers["content-disposition"]
    rows1 = list(csv.reader(io.StringIO(r1.content.decode("utf-8-sig"))))[1:]
    rows2 = list(csv.reader(io.StringIO(r2.content.decode("utf-8-sig"))))[1:]
    assert (len(rows1), len(rows2)) == (5, 3)
    assert {r[1] for r in rows2} == {"Coimbatore Cotton Mills Pvt Ltd", "Surat Yarn Traders", "Chennai Packaging Co."}
    assert not {r[3] for r in rows1} & {r[3] for r in rows2}


def test_correction_email_uses_the_right_business(demo):
    c, *_ = demo
    tirupur = [i for i in c.get("/api/invoices", headers=H2).json() if "Tirupur" in (i["supplier_name"] or "")][0]
    d = c.post(f"/api/invoices/{tirupur['id']}/request-correction", headers=H2).json()
    biz = [b for b in BUSINESSES if b[0] == 2][0]
    assert d["to"] == "billing@tirupurdyeing.example.com"
    assert biz[1] in d["body"] and biz[3] in d["body"] and "Bluebird" not in d["body"]
    assert "CGST + SGST applies" in d["body"]  # Tirupur -> Coimbatore is the same state


def test_msme_timers_for_the_second_business(demo):
    c, *_ = demo
    held = {i["supplier_name"]: i["msme"] for i in c.get("/api/invoices", headers=H2).json() if i["status"] == "HELD"}
    assert held["Tirupur Dyeing Works"]["limit_days"] == 15 and held["Tirupur Dyeing Works"]["days_left"] == 6
    assert held["Chennai Packaging Co."]["state"] == "overdue" and held["Chennai Packaging Co."]["days_left"] == -3


def test_samples_are_per_business(demo):
    c, *_ = demo
    s1, s2 = c.get("/api/samples", headers=H1).json(), c.get("/api/samples", headers=H2).json()
    assert len(s1) == 3 and [s["file"] for s in s2] == ["sample_4_kaveri_valid.pdf"]
    pdf = c.get(s2[0]["url"], headers=H2)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    up = c.post("/api/invoices/upload", headers=H2, files={"file": ("s.pdf", pdf.content, "application/pdf")}).json()
    assert up["status"] == "PAID" and up["business_id"] == 2
    assert len(c.get("/api/invoices", headers=H2).json()) == 8 and len(c.get("/api/invoices", headers=H1).json()) == 13


# ---- the AP agent ----------------------------------------------------------------------------------------------
def test_agent_tools_cannot_see_another_business(demo):
    c, conn, _ = demo
    ids2 = {i["id"] for i in c.get("/api/invoices", headers=H2).json()}
    listed = agent.dispatch(conn, "list_invoices", {}, business_id=2)["invoices"]
    assert {i["id"] for i in listed} == ids2
    mine = c.get("/api/invoices", headers=H1).json()[0]["id"]
    for tool in ("run_checks", "propose_payment"):
        assert agent.dispatch(conn, tool, {"invoice_id": mine}, business_id=2) == {"error": "Invoice not found"}


def test_agent_confirm_cannot_pay_another_businesses_invoice(demo):
    c, conn, sent = demo
    cedar = [i for i in c.get("/api/invoices", headers=H1).json() if i["status"] == "HELD" and "Cedar" in i["supplier_name"]][0]
    before = len(sent)
    res = c.post("/api/agent/confirm", headers=H2, json={"invoice_ids": [cedar["id"]]}).json()["results"]
    assert res == [{"invoice_id": cedar["id"], "paid": False, "message": "Invoice not found"}] and len(sent) == before
    assert conn.execute("SELECT status FROM invoices WHERE id=?", (cedar["id"],)).fetchone()[0] == "HELD"


def test_suggestions_and_recorded_answers_per_business(demo, monkeypatch):
    c, conn, sent = demo
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")  # a live Gemini call would fail
    for bid, h in ((1, H1), (2, H2)):
        chips = c.get("/api/agent/suggestions", headers=h).json()["suggestions"]
        assert len(chips) == 3 and chips == agent.SUGGESTIONS[bid]
        for chip in chips:
            r = c.post("/api/agent", headers=h, json={"message": chip})
            assert r.status_code == 200 and r.json()["cached"] is True, (bid, chip)
    out = c.post("/api/agent", headers=H2, json={"message": agent.SUGGESTIONS[2][2]}).json()
    assert [r["invoice"]["supplier"] for r in out["proposal"]["recommended"]] == ["Chennai Packaging Co."]
    # business 2's recording is not served to business 1 (different state and different business)
    assert agent.cached_run(conn, agent.SUGGESTIONS[2][2], business_id=1) is None


# ---- upgrading an older database ------------------------------------------------------------------------------
def test_old_database_without_business_columns_is_upgraded(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE suppliers (id INTEGER PRIMARY KEY, name TEXT);"
                      "CREATE TABLE invoices (id INTEGER PRIMARY KEY, status TEXT);"
                      "INSERT INTO suppliers VALUES (1, 'Old Supplier'); INSERT INTO invoices VALUES (1, 'PAID');")
    old.commit()
    old.close()
    monkeypatch.setattr(config, "DB_PATH", str(path))
    db.init_db()
    db.init_db()  # safe to run again
    conn = db.connect()
    assert conn.execute("SELECT business_id FROM suppliers").fetchone()[0] == 1
    assert conn.execute("SELECT business_id FROM invoices").fetchone()[0] == 1
    conn.close()


def test_demo_runs_cover_every_business():
    assert {b for b, _ in DEMO_RUNS} == {b[0] for b in BUSINESSES} == {1, 2}
    assert businesses.slug("Kaveri Textiles") == "kaveri-textiles"
