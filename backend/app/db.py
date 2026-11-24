"""SQLite setup. Money is stored as integer cents."""
import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS suppliers (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL UNIQUE,
    approved       INTEGER NOT NULL DEFAULT 1,
    gstin          TEXT NOT NULL,        -- saved GSTIN: an invoice with a different one is blocked
    bank_account   TEXT,                 -- saved payout destination (payouts NEVER use details printed on an invoice)
    ifsc           TEXT,
    upi_id         TEXT,
    payout_method  TEXT NOT NULL DEFAULT 'UPI',   -- UPI or BANK
    notes          TEXT,                 -- address
    email          TEXT,                 -- accounts contact, used to draft correction requests
    msme           TEXT,                 -- NULL, 'micro' or 'small' (Section 43B(h) payment timer)
    msme_written_agreement INTEGER NOT NULL DEFAULT 0   -- 1 = written agreement, so the 45-day limit applies; else 15
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number    TEXT NOT NULL UNIQUE,
    supplier_id  INTEGER NOT NULL REFERENCES suppliers(id),
    amount_paise INTEGER NOT NULL,       -- PO value including GST
    description  TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    filename          TEXT,
    file_hash         TEXT,
    supplier_id       INTEGER REFERENCES suppliers(id),
    supplier_name     TEXT,
    supplier_gstin    TEXT,
    buyer_gstin       TEXT,
    place_of_supply   TEXT,
    invoice_number    TEXT,
    invoice_date      TEXT,
    due_date          TEXT,
    po_number         TEXT,
    taxable_paise     INTEGER,
    cgst_paise        INTEGER,
    sgst_paise        INTEGER,
    igst_paise        INTEGER,
    total_paise       INTEGER,
    payee_upi         TEXT,              -- payment details PRINTED on the invoice (compared with the saved ones)
    payee_account     TEXT,
    payee_ifsc        TEXT,
    line_items        TEXT,              -- JSON
    gst_report        TEXT,              -- JSON: every GST check with pass/fail, shown per invoice in the dashboard
    status            TEXT NOT NULL DEFAULT 'RECEIVED',  -- RECEIVED/PAID/HELD/BLOCKED/REJECTED
    decision          TEXT,              -- AUTO_PAY / HOLD / BLOCK
    reason            TEXT,
    risk_score        REAL,
    payout_ref        TEXT,              -- our idempotency key for the payout
    payout_batch_id   TEXT,              -- payout id returned by the payout provider
    payout_status     TEXT,              -- PENDING / SUCCESS / FAILED
    payout_method     TEXT,              -- UPI / IMPS / RTGS
    payout_destination TEXT,             -- masked, e.g. ra***@okhdfc or XXXXXX1234
    paid_at           TEXT,              -- when the payout was sent (for the daily limit)
    accepted_date     TEXT,              -- IST date the invoice was accepted; the MSME payment clock starts here
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id  INTEGER REFERENCES invoices(id),
    event       TEXT NOT NULL,
    decision    TEXT,
    reason      TEXT,
    details     TEXT,                    -- JSON
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS gemini_cache (
    file_hash   TEXT NOT NULL,
    kind        TEXT NOT NULL,           -- 'extract' or 'review'
    result_json TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (file_hash, kind)
);

CREATE TABLE IF NOT EXISTS payouts (       -- the simulated sandbox's ledger; `ref` makes a payout idempotent
    ref          TEXT PRIMARY KEY,
    payout_id    TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    method       TEXT NOT NULL,
    destination  TEXT NOT NULL,            -- masked
    status       TEXT NOT NULL,
    utr          TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)  # one connection per request, may hop threads
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if missing. Safe to run on every startup."""
    with connect() as conn:
        conn.executescript(SCHEMA)


def is_empty() -> bool:
    """True when there are no suppliers (used on startup to decide whether to re-seed)."""
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0] == 0
