"""Payout adapter: pays the supplier's SAVED UPI ID or bank account (never details printed on an invoice).

Only one provider exists today: "simulated", a clearly labelled sandbox. No real money moves and no bank is
contacted. Its ledger (the `payouts` table) gives it the behaviour a real rail has:
  * idempotency: the same `ref` always returns the same payout, so a retry can never pay twice;
  * failures: insufficient sandbox funds, a rejected beneficiary (UPI id or account containing "fail"),
    an amount over the UPI limit with no bank account to fall back on.
A real provider (for example RazorpayX Payouts or a bank API) would implement send_payout/get_payout_status with the
same signatures and be selected with PAYOUT_PROVIDER; pipeline.py would not change.
"""
import secrets

from . import config
from .money import inr

SANDBOX_LABEL = "SIMULATED SANDBOX - no real money moves"
UPI_LIMIT_PAISE = 10000000       # Rs 1,00,000 per UPI payment
IMPS_LIMIT_PAISE = 20000000      # Rs 2,00,000 per IMPS payment; above that the bank rail is RTGS


class PayoutError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code  # e.g. INSUFFICIENT_FUNDS, BENEFICIARY_REJECTED, NO_DESTINATION


def mask_upi(upi: str) -> str:
    name, _, handle = upi.partition("@")
    return f"{name[:2]}***@{handle}"


def mask_account(account: str) -> str:
    return "X" * max(len(account) - 4, 0) + account[-4:]


def destination_for(supplier, amount_paise: int) -> dict:
    """Pick the payout rail from the supplier's SAVED details. Raises PayoutError if none can take this amount."""
    upi = (supplier["upi_id"] or "").strip()
    account, ifsc = (supplier["bank_account"] or "").strip(), (supplier["ifsc"] or "").strip()
    has_bank = bool(account and ifsc)
    prefer_upi = supplier["payout_method"] == "UPI" and upi
    if prefer_upi and amount_paise <= UPI_LIMIT_PAISE:
        return {"method": "UPI", "upi_id": upi, "masked": mask_upi(upi)}
    if has_bank:
        return {"method": "IMPS" if amount_paise <= IMPS_LIMIT_PAISE else "RTGS", "account": account, "ifsc": ifsc,
                "masked": mask_account(account)}
    if prefer_upi:
        raise PayoutError(f"{inr(amount_paise)} is over the UPI limit of {inr(UPI_LIMIT_PAISE)} and the supplier "
                          "has no bank account saved", "UPI_LIMIT")
    raise PayoutError("The supplier has no saved UPI ID or bank account to pay", "NO_DESTINATION")


def _ledger_total(conn) -> int:
    return conn.execute("SELECT COALESCE(SUM(amount_paise), 0) FROM payouts").fetchone()[0]


def send_payout(conn, ref: str, destination: dict, amount_paise: int, note: str) -> dict:
    """Send one payout. Returns {"batch_id", "status": PENDING/SUCCESS/FAILED, "method", "destination", "sandbox"}.
    Idempotent on `ref`."""
    if config.PAYOUT_PROVIDER != "simulated":
        raise PayoutError(f"Payout provider '{config.PAYOUT_PROVIDER}' is not available; only 'simulated' is built in",
                          "NO_PROVIDER")
    existing = conn.execute("SELECT * FROM payouts WHERE ref = ?", (ref,)).fetchone()
    if existing:  # the same request again: return the first result, send nothing new
        return {"batch_id": existing["payout_id"], "status": existing["status"], "method": existing["method"],
                "destination": existing["destination"], "sandbox": True}
    target = destination.get("upi_id") or destination.get("account") or ""
    if "fail" in target.lower():
        raise PayoutError("The bank rejected the beneficiary account (sandbox test case)", "BENEFICIARY_REJECTED")
    if _ledger_total(conn) + amount_paise > config.SANDBOX_BALANCE_PAISE:
        raise PayoutError("Insufficient funds in the sandbox payout wallet", "INSUFFICIENT_FUNDS")
    payout_id = f"SIM-{ref}"
    conn.execute("INSERT INTO payouts (ref, payout_id, amount_paise, method, destination, status) "
                 "VALUES (?, ?, ?, ?, ?, 'PENDING')",
                 (ref, payout_id, amount_paise, destination["method"], destination["masked"]))
    conn.commit()
    return {"batch_id": payout_id, "status": "PENDING", "method": destination["method"],
            "destination": destination["masked"], "sandbox": True}


def get_payout_status(conn, payout_id: str) -> str:
    """Simulated settlement: a PENDING payout becomes SUCCESS (with a made-up UTR) the first time it is checked."""
    row = conn.execute("SELECT * FROM payouts WHERE payout_id = ?", (payout_id,)).fetchone()
    if row is None:
        raise PayoutError("Unknown payout id", "NOT_FOUND")
    if row["status"] == "PENDING":
        conn.execute("UPDATE payouts SET status='SUCCESS', utr=? WHERE payout_id=?",
                     ("SIMUTR" + secrets.token_hex(5).upper(), payout_id))
        conn.commit()
        return "SUCCESS"
    return row["status"]
