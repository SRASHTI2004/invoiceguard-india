"""Evaluation: run every sample invoice through InvoiceGuard and report how many fraud cases were caught
and how many valid invoices were wrongly held/blocked.

Run from backend/:
    python -m eval.run_eval                 # fresh temp DB, cached Gemini results (instant, no quota)
    python -m eval.run_eval --live-gemini   # ignore the cache and call Gemini for real (uses free-tier quota)
    python -m eval.run_eval --write         # also (re)write eval/results.json, the file the app's "How well it works" page shows
Payouts always go to the simulated sandbox: no real money moves.
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app import config, db, decide, pipeline
from app.money import inr
from seed.seed import seed_db

SEED = Path(__file__).resolve().parents[1] / "seed"
RESULTS_FILE = Path(__file__).resolve().parent / "results.json"

# Plain-English name of the check behind each finding code, for the "which check caught it" column.
CHECK_NAMES = {
    "duplicate_number": "Duplicate invoice check", "duplicate_amount_date": "Duplicate invoice check",
    "supplier_gstin_invalid": "GSTIN check character", "supplier_gstin_mismatch": "GSTIN matches saved supplier",
    "buyer_gstin_mismatch": "Buyer GSTIN check", "wrong_tax_type": "Tax type (CGST+SGST vs IGST)",
    "place_of_supply_unknown": "Place of supply", "hsn_invalid": "HSN / SAC codes", "gst_rate_invalid": "GST rate slabs",
    "taxable_mismatch": "GST arithmetic (taxable value)", "gst_amount_wrong": "GST arithmetic (GST amount)",
    "cgst_sgst_unequal": "GST arithmetic (CGST = SGST)", "gst_total_wrong": "GST arithmetic (invoice total)",
    "payee_changed": "Payee check (saved UPI ID or account)", "unknown_supplier": "Approved supplier list",
    "unapproved_supplier": "Approved supplier list", "po_not_found": "Purchase order check",
    "po_wrong_supplier": "Purchase order check", "over_po": "Purchase order check", "under_po": "Purchase order check",
    "no_po": "Purchase order check", "over_payment_limit": "Payment limits", "over_daily_limit": "Payment limits",
    "missing_fields": "Invoice reading", "no_line_items": "Invoice reading", "bad_line_items": "Invoice reading",
    "extraction_failed": "Invoice reading",
}


def fired_checks(conn, invoice_id: int) -> list[dict]:
    """Every check that raised a problem for this invoice (from the audit log of the real run), most serious first."""
    row = conn.execute("SELECT details FROM audit_log WHERE invoice_id=? AND event='decision' ORDER BY id LIMIT 1",
                       (invoice_id,)).fetchone()
    d = json.loads(row["details"]) if row and row["details"] else {}
    out = [{"name": CHECK_NAMES.get(f["code"], f["code"]), "severity": f["severity"], "message": f["message"]}
           for f in d.get("findings") or []]
    ai = d.get("ai_review")
    if ai and ai["risk_score"] >= decide.AI_HOLD_RISK:
        out.append({"name": "AI review (scam / hidden instructions)",
                    "severity": "BLOCK" if ai["risk_score"] >= decide.AI_BLOCK_RISK else "HOLD",
                    "message": "; ".join(ai.get("reasons") or []) or f"risk score {ai['risk_score']:.2f}"})
    return sorted(out, key=lambda c: c["severity"] != "BLOCK")  # BLOCK first, stable otherwise


def evaluate(conn, labels: list[dict]) -> dict:
    """Process the labelled PDFs in order and compare each decision with the ground truth."""
    rows = []
    for lab in labels:
        inv = pipeline.process_invoice(conn, (SEED / "invoices" / lab["file"]).read_bytes(), lab["file"])
        rows.append({**lab, "invoice_id": inv["id"], "decision": inv["decision"], "status": inv["status"],
                     "reason": inv["reason"], "amount_paise": inv["total_paise"] or 0,
                     "checks": fired_checks(conn, inv["id"])})
    fraud = [r for r in rows if r["is_fraud"]]
    valid = [r for r in rows if not r["is_fraud"]]
    caught = [r for r in fraud if r["decision"] != "AUTO_PAY"]
    wrongly_held = [r for r in valid if r["decision"] != "AUTO_PAY"]
    return {
        "rows": rows,
        "fraud_total": len(fraud), "fraud_caught": len(caught),
        "valid_total": len(valid), "valid_wrongly_held": len(wrongly_held),
        "fraud_paise_stopped": sum(r["amount_paise"] for r in caught),
        "fraud_paise_total": sum(r["amount_paise"] for r in fraud),
        "valid_paise_paid": sum(r["amount_paise"] for r in valid if r["decision"] == "AUTO_PAY"),
    }


def build_report(result: dict, live_gemini: bool = False) -> dict:
    """The JSON the app shows on its 'How well it works' page, built from a real run of evaluate()."""
    cases = []
    for n, r in enumerate(result["rows"], 1):
        caught = r["decision"] != "AUTO_PAY"
        cases.append({
            "n": n, "file": r["file"], "supplier": r["supplier"], "invoice_number": r["number"], "category": r["category"],
            "is_fraud": r["is_fraud"], "expected": r["expected"], "decision": r["decision"], "status": r["status"],
            "correct": caught == r["is_fraud"], "amount_paise": r["amount_paise"],
            "primary_check": r["checks"][0]["name"] if r["checks"] else None,
            "checks": r["checks"], "reason": r["reason"],
        })
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "generator": "python -m eval.run_eval --write",
        "method": ("Every labelled sample invoice is run through the full pipeline in a fresh database. "
                   + ("Gemini was called live." if live_gemini else "Gemini results are the cached real model output in seed/gemini_cache.json.")
                   + " Payouts are the simulated sandbox."),
        "summary": {
            "cases": len(cases), "fraud_total": result["fraud_total"], "fraud_caught": result["fraud_caught"],
            "valid_total": result["valid_total"], "valid_wrongly_held": result["valid_wrongly_held"],
            "fraud_amount_paise": result["fraud_paise_total"], "fraud_stopped_paise": result["fraud_paise_stopped"],
            "valid_paid_paise": result["valid_paise_paid"],
        },
        "cases": cases,
    }


def run(live_gemini: bool = False) -> dict:
    """Run the whole evaluation in a throwaway database and return evaluate()'s result."""
    labels = json.loads((SEED / "labels.json").read_text())
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        config.DB_PATH = str(Path(tmp) / "eval.db")  # never touches your real database
        seed_db(use_cached_gemini=not live_gemini)
        conn = db.connect()
        result = evaluate(conn, labels)
        conn.close()
    return result


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # the rupee sign on a Windows console
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-gemini", action="store_true", help="ignore the cache and call Gemini")
    ap.add_argument("--write", action="store_true", help="write eval/results.json (shown in the app)")
    args = ap.parse_args()
    result = run(args.live_gemini)
    if args.write:
        RESULTS_FILE.write_text(json.dumps(build_report(result, args.live_gemini), indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {RESULTS_FILE}")

    money = inr
    print(f"\n{'file':40} {'expected':14} {'decision':9} reason")
    for r in result["rows"]:
        ok = (r["decision"] == "AUTO_PAY") == (not r["is_fraud"])
        print(f"{'OK ' if ok else 'BAD'} {r['file']:37} {r['expected']:14} {r['decision']:9} {(r['reason'] or '')[:100]}")
    print("\n=== InvoiceGuard India evaluation ===")
    for cat in dict.fromkeys(r["category"] for r in result["rows"] if r["is_fraud"]):
        row = next(r for r in result["rows"] if r["category"] == cat)
        print(f"  {cat:22} {'caught' if row['decision'] != 'AUTO_PAY' else 'MISSED':7} -> {row['decision']}")
    print(f"Fraud cases caught:             {result['fraud_caught']} / {result['fraud_total']}")
    print(f"Valid invoices wrongly held:    {result['valid_wrongly_held']} / {result['valid_total']}")
    print(f"Fraudulent money stopped:       {money(result['fraud_paise_stopped'])} of {money(result['fraud_paise_total'])}")
    print(f"Valid invoices paid:            {money(result['valid_paise_paid'])}")
    print(f"(Payouts: simulated sandbox; Gemini: {'live calls' if args.live_gemini else 'cached results'})")


if __name__ == "__main__":
    main()
