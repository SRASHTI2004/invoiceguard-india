import json

from app import config, db
from app.money import inr
from eval import run_eval
from seed.data import INVOICES, compute
from seed.seed import seed_db


def test_eval_metrics_on_sample_invoices(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    seed_db()
    labels = json.loads((run_eval.SEED / "labels.json").read_text())
    conn = db.connect()
    r = run_eval.evaluate(conn, labels)
    assert (r["fraud_caught"], r["fraud_total"]) == (7, 7)
    assert (r["valid_wrongly_held"], r["valid_total"]) == (0, 5)
    assert r["valid_paise_paid"] == sum(compute(i)["total"] for i in INVOICES if not i["is_fraud"])
    assert inr(r["valid_paise_paid"]) == "₹7,16,077.00"
    assert r["fraud_paise_stopped"] == r["fraud_paise_total"]
    # the fraud categories the demo promises are all in the eval
    assert {x["category"] for x in r["rows"] if x["is_fraud"]} >= {
        "fake_gstin", "wrong_tax_type", "wrong_gst_total", "duplicate", "changed_payee", "prompt_injection"}
    conn.close()
