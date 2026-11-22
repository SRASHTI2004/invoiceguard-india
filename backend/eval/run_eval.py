"""Evaluation: run every sample invoice through InvoiceGuard and report how many fraud cases were caught
and how many valid invoices were wrongly held/blocked.

Run from backend/:
    python -m eval.run_eval                 # fresh temp DB, cached Gemini results (instant, no quota)
    python -m eval.run_eval --live-gemini   # ignore the cache and call Gemini for real (uses free-tier quota)
Payouts always go to the simulated sandbox: no real money moves.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

from app import config, db, pipeline
from app.money import inr
from seed.seed import seed_db

SEED = Path(__file__).resolve().parents[1] / "seed"


def evaluate(conn, labels: list[dict]) -> dict:
    """Process the labelled PDFs in order and compare each decision with the ground truth."""
    rows = []
    for lab in labels:
        inv = pipeline.process_invoice(conn, (SEED / "invoices" / lab["file"]).read_bytes(), lab["file"])
        rows.append({**lab, "decision": inv["decision"], "status": inv["status"], "reason": inv["reason"],
                     "amount_paise": inv["total_paise"] or 0})
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


def main():
    sys.stdout.reconfigure(encoding="utf-8")  # the rupee sign on a Windows console
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-gemini", action="store_true", help="ignore the cache and call Gemini")
    args = ap.parse_args()

    labels = json.loads((SEED / "labels.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        config.DB_PATH = str(Path(tmp) / "eval.db")  # never touches your real database
        seed_db(use_cached_gemini=not args.live_gemini)
        conn = db.connect()
        result = evaluate(conn, labels)
        conn.close()

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
