from datetime import date, timedelta

from fastapi.testclient import TestClient

from app import msme, timeutil
from app.main import app
from seed.data import ACCEPTED_AGO, SUPPLIERS
from tests.test_pipeline import run

TODAY = date(2026, 11, 24)


def sup(msme_class="small", agreement=1):
    return {"msme": msme_class, "msme_written_agreement": agreement}


def test_limit_is_45_days_with_a_written_agreement_and_15_without():
    a = msme.deadline(sup(agreement=1), "2026-11-04", TODAY)
    assert (a["limit_days"], a["pay_by"], a["days_left"]) == (45, "2026-12-19", 25)
    b = msme.deadline(sup("micro", 0), "2026-11-04", TODAY)
    assert (b["limit_days"], b["pay_by"], b["days_left"], b["class"]) == (15, "2026-11-19", -5, "micro")


def test_states_ok_soon_overdue_and_the_boundaries():
    def state(days_left):  # accepted so that exactly `days_left` days remain on a 15-day clock
        accepted = TODAY - timedelta(days=15 - days_left)
        return msme.deadline(sup("micro", 0), accepted.isoformat(), TODAY)["state"]
    assert state(8) == "ok" and state(7) == "soon" and state(1) == "soon" and state(0) == "soon"
    assert state(-1) == "overdue"


def test_message_is_plain_english():
    soon = msme.deadline(sup(agreement=1), "2026-10-15", TODAY)  # 45 days -> pay by 29 Nov -> 5 days left
    assert "5 days left" in soon["message"] and "29 Nov 2026" in soon["message"] and "45-day limit" in soon["message"]
    assert "overdue by 5 days" in msme.deadline(sup("micro", 0), "2026-11-04", TODAY)["message"]
    assert "due today" in msme.deadline(sup("micro", 0), "2026-11-09", TODAY)["message"]
    assert "not tax advice" in soon["note"].lower() and "43B(h)" in soon["note"]


def test_non_msme_and_missing_dates_have_no_timer():
    assert msme.deadline(sup(None, 0), "2026-11-04", TODAY) is None
    assert msme.deadline(sup(), None, TODAY) is None
    assert msme.deadline(sup(), "not-a-date", TODAY) is None
    assert msme.deadline(None, "2026-11-04", TODAY) is None


def test_demo_data_marks_msme_suppliers():
    classes = {s[0]: (s[9], s[10]) for s in SUPPLIERS}
    assert classes["Pinnacle Print & Design"] == ("micro", 0)
    assert classes["Cedar & Pine Furniture"] == ("small", 1)
    assert classes["Summit IT Services Pvt Ltd"] == (None, 0)
    assert sum(1 for v in classes.values() if v[0]) >= 5


def test_demo_run_sets_acceptance_dates_so_the_timers_are_meaningful(env):
    conn, _ = env
    with TestClient(app) as c:
        c.post("/api/demo/run-samples")
        listed = c.get("/api/invoices").json()
        held = {i["supplier_name"]: i for i in listed if i["status"] == "HELD"}
        today = timeutil.today_ist()
        cedar_inv = held["Cedar & Pine Furniture"]
        assert today - date.fromisoformat(cedar_inv["accepted_date"]) == timedelta(days=ACCEPTED_AGO["inv13_cedarpine_partial.pdf"])
        cedar, pin, orch = (held[n]["msme"] for n in ("Cedar & Pine Furniture", "Pinnacle Print & Design", "Orchard Catering Services"))
        assert (cedar["days_left"], cedar["state"], cedar["limit_days"]) == (5, "soon", 45)
        assert (pin["days_left"], pin["state"], pin["limit_days"]) == (2, "soon", 15)
        assert (orch["days_left"], orch["state"]) == (25, "ok")
        paid = [i for i in listed if i["status"] == "PAID"]
        assert paid and all(i["msme"] is None for i in paid)  # the timer is only for unpaid invoices


def test_uploaded_invoice_is_accepted_today(env):
    conn, _ = env
    inv = run(conn, "inv13_cedarpine_partial.pdf")
    assert conn.execute("SELECT accepted_date FROM invoices WHERE id=?", (inv["id"],)).fetchone()[0] == timeutil.today_ist().isoformat()


def test_suppliers_endpoint_reports_msme(env):
    with TestClient(app) as c:
        by = {s["name"]: s for s in c.get("/api/suppliers").json()}
    assert by["Pinnacle Print & Design"]["msme"] == "micro" and by["Pinnacle Print & Design"]["msme_written_agreement"] == 0
    assert by["Konkan Freight Logistics"]["msme"] is None
