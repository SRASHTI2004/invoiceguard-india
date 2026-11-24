import json

from fastapi.testclient import TestClient

from app import config
from app.main import app
from eval import run_eval


def committed():
    return json.loads(run_eval.RESULTS_FILE.read_text(encoding="utf-8"))


def strip(report):
    return {k: v for k, v in report.items() if k != "generated_at"}


def test_committed_results_match_a_fresh_real_run(tmp_path, monkeypatch):
    """The page shows eval/results.json. This fails if the file is stale, so the page can never drift from the code."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "e.db"))
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "DB_PATH", config.DB_PATH)  # restore the original path after run() changes it
    fresh = run_eval.build_report(run_eval.run())
    assert strip(fresh) == strip(committed()), "eval/results.json is stale: run `python -m eval.run_eval --write`"


def test_report_content(tmp_path, monkeypatch):
    d = committed()
    s = d["summary"]
    assert (s["fraud_caught"], s["fraud_total"], s["valid_wrongly_held"], s["valid_total"]) == (7, 7, 0, 5)
    assert s["fraud_stopped_paise"] == s["fraud_amount_paise"] and s["cases"] == len(d["cases"]) == 12
    assert all(c["correct"] for c in d["cases"])
    by = {c["category"]: c for c in d["cases"]}
    assert by["fake_gstin"]["primary_check"] == "GSTIN check character"
    assert by["wrong_tax_type"]["primary_check"] == "Tax type (CGST+SGST vs IGST)" and by["wrong_tax_type"]["decision"] == "HOLD"
    assert by["wrong_gst_total"]["primary_check"] == "GST arithmetic (invoice total)"
    assert by["changed_payee"]["primary_check"] == "Payee check (saved UPI ID or account)"
    assert by["duplicate"]["primary_check"] == "Duplicate invoice check"
    assert by["prompt_injection"]["primary_check"].startswith("AI review")
    assert by["unapproved_supplier"]["primary_check"] == "Approved supplier list"
    assert all(c["checks"] == [] and c["primary_check"] is None for c in d["cases"] if not c["is_fraud"])  # valid: nothing fired


def test_endpoint_serves_the_file():
    with TestClient(app) as c:
        r = c.get("/api/evaluation").json()
    assert r["available"] is True and r["summary"]["fraud_caught"] == 7 and len(r["cases"]) == 12
    assert "cached real model output" in r["method"] or "Gemini was called live" in r["method"]
