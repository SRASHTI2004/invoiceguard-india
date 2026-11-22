"""Settings loaded from the environment / .env file. Never print or log secret values."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")



def _secret(name: str) -> str:
    """Read a secret and strip leading/trailing whitespace and quotes (pasted spaces or newlines break auth)."""
    return os.getenv(name, "").strip().strip("\"'").strip()


GEMINI_API_KEY = _secret("GEMINI_API_KEY")
# Comma-separated list: tried in order. The free tier allows only ~20 requests/day per model,
# so later models act as fallbacks when one is out of quota or overloaded.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash,gemini-3.1-flash-lite,gemini-3.8-flash")
# Payouts go through app/payouts.py. "simulated" is a clearly labelled sandbox: no real money moves.
PAYOUT_PROVIDER = os.getenv("PAYOUT_PROVIDER", "simulated").lower()
# Simulated sandbox wallet balance in paise (default Rs 2 crore). Payouts beyond it fail with INSUFFICIENT_FUNDS.
SANDBOX_BALANCE_PAISE = int(os.getenv("SANDBOX_BALANCE_PAISE", "2000000000"))

# The demo reset endpoint can be rate-limited (seconds between runs). 0 = unlimited, fine for the simulated sandbox.
DEMO_COOLDOWN_SECONDS = int(os.getenv("DEMO_COOLDOWN_SECONDS", "0"))

# Our company (the buyer). Invoices must be billed to this GSTIN or they are held (we could not claim input tax credit).
BUYER_NAME = os.getenv("BUYER_NAME", "Bluebird Retail Pvt Ltd")
BUYER_GSTIN = os.getenv("BUYER_GSTIN", "29AABCB5521M1ZJ").strip().upper()

DB_PATH = os.getenv("DB_PATH", str(ROOT / "backend" / "invoiceguard.db"))

# Limits are in paise (1 rupee = 100 paise) to avoid float rounding problems.
CURRENCY = "INR"
PER_PAYMENT_LIMIT_PAISE = int(os.getenv("PER_PAYMENT_LIMIT_PAISE", "50000000"))  # Rs 5,00,000
DAILY_LIMIT_PAISE = int(os.getenv("DAILY_LIMIT_PAISE", "150000000"))  # Rs 15,00,000


def secrets_status() -> dict[str, bool]:
    """Which secrets are set (booleans only, never the values)."""
    return {
        "GEMINI_API_KEY": bool(GEMINI_API_KEY),
    }


def secret_lengths() -> dict[str, int]:
    """Length of each secret after trimming (never the value), to spot pasted spaces or truncated keys."""
    return {"GEMINI_API_KEY": len(GEMINI_API_KEY)}
