"""Build seed/gemini_cache.json (committed): Gemini's extraction + review result for every sample PDF, so the demo,
the eval and a fresh deploy answer instantly with zero Gemini calls for these files. Run from backend/:

    python -m seed.export_cache               # call Gemini live (needs GEMINI_API_KEY) for PDFs not yet cached
    python -m seed.export_cache --synthesize  # offline: write what Gemini SHOULD return, derived from the sample data

--synthesize output is NOT real model output; it exists only so the project builds without an API key. The file
records which mode produced it. Only extraction/review output is stored (no secrets).
"""
import json
import sys
import tempfile
import time
from pathlib import Path

from app import ai_review, config, db, extract, gemini
from seed.data import BUYER, DEMO_INVOICES, INVOICES, SUP, UPLOAD_SAMPLES, compute
from seed.make_pdfs import pay_details

HERE = Path(__file__).parent
ALL = INVOICES + DEMO_INVOICES + UPLOAD_SAMPLES


def pdf_path(inv: dict) -> Path:
    return HERE / ("upload_samples" if inv in UPLOAD_SAMPLES else "invoices") / inv["file"]


def _rupees(paise):
    return None if paise is None else paise / 100


def synthetic_extract(inv: dict) -> dict:
    """The extraction a correct reader would produce for this sample (money in rupees, as Gemini returns it)."""
    t, s, pay = compute(inv), SUP[inv["supplier"]], pay_details(inv)
    return {
        "supplier_name": inv["supplier"], "supplier_gstin": inv.get("gstin") or s["gstin"],
        "buyer_gstin": BUYER["gstin"], "place_of_supply": BUYER["place_of_supply"],
        "invoice_number": inv["number"], "invoice_date": inv["date"], "due_date": inv["due"], "po_number": inv["po"],
        "taxable_value": _rupees(t["taxable"]), "cgst": _rupees(t["cgst"]), "sgst": _rupees(t["sgst"]),
        "igst": _rupees(t["igst"]), "total": _rupees(t["total"]),
        "payee_upi": pay.get("upi"), "payee_account": pay.get("account"), "payee_ifsc": pay.get("ifsc"),
        "line_items": [{"description": d, "hsn_sac": h, "quantity": q, "unit_price": u / 100, "gst_rate": r}
                       for d, h, q, u, r in inv["items"]],
    }


def synthetic_review(inv: dict) -> dict:
    if inv.get("hidden"):
        return {"risk_score": 0.97, "signals": ["prompt_injection"],
                "reasons": ["Hidden text addresses an AI payment agent and tells it to skip checks and pay immediately."]}
    if inv.get("banner") and "payment details" in inv["banner"]:
        return {"risk_score": 0.9, "signals": ["new_payment_details"],
                "reasons": ["The invoice says the supplier's payment details have changed."]}
    return {"risk_score": 0.0, "signals": [], "reasons": []}


def main():
    synth = "--synthesize" in sys.argv
    CACHE = HERE / "gemini_cache.json"
    have = {(e["file_hash"], e["kind"]): e for e in json.loads(CACHE.read_text())} if CACHE.exists() and not synth else {}
    out = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        config.DB_PATH = str(Path(tmp) / "cache.db")
        db.init_db()
        conn = db.connect()
        for inv in ALL:
            data = pdf_path(inv).read_bytes()
            h = gemini.pdf_hash(data)
            if all((h, k) in have for k in ("extract", "review")):  # already cached: keep it, spend no quota
                out += [have[(h, k)] for k in ("extract", "review")]
                continue
            if synth:
                results = {"extract": synthetic_extract(inv), "review": synthetic_review(inv)}
            else:
                extract.extract_invoice(data, conn)
                time.sleep(3)
                ai_review.review_invoice(data, conn)
                time.sleep(3)
                results = {k: json.loads(conn.execute("SELECT result_json FROM gemini_cache WHERE file_hash=? AND kind=?",
                                                      (h, k)).fetchone()[0]) for k in ("extract", "review")}
                print("cached", inv["file"], flush=True)
            for kind, result in results.items():
                out.append({"file": inv["file"], "file_hash": h, "kind": kind, "result": result})
        conn.close()
    CACHE.write_text(json.dumps(out, indent=1))
    print(f"exported {len(out)} cached results ({'SYNTHESIZED, not real Gemini output' if synth else 'live Gemini'})")


if __name__ == "__main__":
    main()
