from pathlib import Path

from fastapi.testclient import TestClient

from app import pipeline
from app.main import app
from seed.data import INVOICES, UPLOAD_SAMPLES, compute

DIR = Path(__file__).parents[1] / "seed" / "upload_samples"


def upload(client, name):
    return client.post("/api/invoices/upload", files={"file": (name, (DIR / name).read_bytes(), "application/pdf")})


def test_listing_and_download(env):
    with TestClient(app) as c:
        listed = c.get("/api/samples").json()
        assert [s["file"] for s in listed] == [s["file"] for s in UPLOAD_SAMPLES] and len(listed) == 3
        assert {s["expected"] for s in listed} == {"Paid", "On hold"} and all(s["description"] for s in listed)
        r = c.get(listed[0]["url"])
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
        assert "attachment" in r.headers["content-disposition"]
        # only the whitelisted files can be fetched
        assert c.get("/api/samples/..%2Fgemini_cache.json").status_code == 404
        assert c.get("/api/samples/inv01_mahalaxmi.pdf").status_code == 404


def test_uploading_each_sample_gives_the_promised_result(env):
    conn, sent = env
    with TestClient(app) as c:
        a, b, g = (upload(c, s["file"]).json() for s in UPLOAD_SAMPLES)
    assert (a["status"], b["status"]) == ("PAID", "PAID") and a["payout_method"] and b["payout_method"]
    assert g["status"] == "HELD" and "Wrong tax type" in g["reason"] and "IGST" in g["reason"]
    assert [x["failed"] for x in [{"failed": [c["code"] for c in g["gst_report"] if not c["ok"]]}]] == [["wrong_tax_type"]]
    assert len(sent) == 2
    assert a["total_paise"] == compute(UPLOAD_SAMPLES[0])["total"]  # matches its own purchase order


def test_samples_work_after_the_demo_data_is_loaded_and_a_repeat_is_a_duplicate(env):
    conn, _ = env
    with TestClient(app) as c:
        c.post("/api/demo/run-samples")
        first = upload(c, UPLOAD_SAMPLES[0]["file"]).json()
        again = upload(c, UPLOAD_SAMPLES[0]["file"]).json()
    assert first["status"] == "PAID" and again["status"] == "BLOCKED" and "Duplicate" in again["reason"]


def test_samples_do_not_leak_into_the_demo_run_or_eval():
    names = {i["file"] for i in INVOICES}
    assert not names & {s["file"] for s in UPLOAD_SAMPLES}
    assert not list(Path(__file__).parents[1].joinpath("seed", "invoices").glob("sample_*"))
