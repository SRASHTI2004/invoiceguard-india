import json
from pathlib import Path

from app import config, db, gemini, gst
from seed.data import BUYER, DEMO_INVOICES, INVOICES, PURCHASE_ORDERS, SUP, SUPPLIERS, compute
from seed.seed import seed_db

SEED = Path(__file__).parents[1] / "seed"


def test_seed_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    assert seed_db() is True
    assert seed_db() is False  # second call does nothing
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == len(SUPPLIERS)
        assert conn.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0] == len(PURCHASE_ORDERS)


def test_supplier_and_buyer_gstins_are_valid_and_match_the_config():
    assert gst.validate_gstin(BUYER["gstin"])[0] and BUYER["gstin"] == config.BUYER_GSTIN
    for name, _, gstin, *_ in SUPPLIERS:
        assert gst.validate_gstin(gstin)[0], name
    for name, approved, gstin, account, ifsc, upi, method, *_ in SUPPLIERS:
        assert (method == "UPI" and upi) or (method == "BANK" and account and ifsc), name


def test_sample_invoices_are_consistent():
    names = {s[0] for s in SUPPLIERS}
    for inv in INVOICES + DEMO_INVOICES:
        assert inv["supplier"] in names
        t = compute(inv)
        assert t["taxable"] == sum(q * u for _, _, q, u, _ in inv["items"])
        assert all(len(h) in (4, 6, 8) for _, h, *_ in inv["items"])
    assert 8 <= len(INVOICES) <= 14
    assert any(i["category"] == "prompt_injection" and i.get("hidden") for i in INVOICES)


def test_each_fraud_sample_has_the_defect_it_claims():
    by_cat = {i["category"]: i for i in INVOICES}
    assert not gst.validate_gstin(by_cat["fake_gstin"]["gstin"])[0]
    assert all(gst.validate_gstin(SUP[i["supplier"]]["gstin"])[0] for i in INVOICES)
    wrong_type = compute(by_cat["wrong_tax_type"])
    assert wrong_type["cgst"] and wrong_type["sgst"] and not wrong_type["igst"]  # inter-state, yet CGST + SGST
    t = compute(by_cat["wrong_gst_total"])
    assert t["total"] != t["taxable"] + t["igst"] + t["cgst"] + t["sgst"]
    assert by_cat["changed_payee"]["pay"]["upi"] != SUP[by_cat["changed_payee"]["supplier"]]["upi"]
    dup = by_cat["duplicate"]
    assert any(i["number"] == dup["number"] and i["supplier"] == dup["supplier"] and i is not dup for i in INVOICES)


def test_valid_samples_cover_both_tax_types():
    valid = [compute(i) for i in INVOICES if not i["is_fraud"]]
    assert any(v["igst"] for v in valid) and any(v["cgst"] and v["sgst"] for v in valid)


def test_labels_file_matches_the_invoice_data():
    labels = json.loads((SEED / "labels.json").read_text())
    assert [l["file"] for l in labels] == [i["file"] for i in INVOICES]
    assert all((SEED / "invoices" / i["file"]).exists() for i in INVOICES + DEMO_INVOICES)


def test_sample_pdfs_are_pre_cached_so_no_gemini_call_is_needed(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    seed_db()
    with db.connect() as conn:
        for inv in INVOICES + DEMO_INVOICES:
            h = gemini.pdf_hash((SEED / "invoices" / inv["file"]).read_bytes())
            kinds = {r[0] for r in conn.execute("SELECT kind FROM gemini_cache WHERE file_hash = ?", (h,))}
            assert kinds == {"extract", "review"}, inv["file"]
