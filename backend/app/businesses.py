"""Client businesses. A CA firm manages several small businesses from one login; each business has its own GSTIN,
suppliers, purchase orders, invoices and audit trail, and nothing is shared between them. Business 1 is the default
when a request does not say which business it is for."""
import re

DEFAULT_ID = 1


def get(conn, business_id: int):
    return conn.execute("SELECT * FROM businesses WHERE id = ?", (business_id,)).fetchone()


def all_with_counts(conn) -> list[dict]:
    """Every business with its invoice and on-hold counts, for the switcher."""
    out = []
    for b in conn.execute("SELECT * FROM businesses ORDER BY id"):
        n, held = conn.execute("SELECT COUNT(*), COALESCE(SUM(status = 'HELD'), 0) FROM invoices WHERE business_id = ?",
                               (b["id"],)).fetchone()
        out.append({"id": b["id"], "name": b["name"], "short_name": b["short_name"], "gstin": b["gstin"],
                    "city": b["city"], "invoice_count": n, "held_count": held})
    return out


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "business"
