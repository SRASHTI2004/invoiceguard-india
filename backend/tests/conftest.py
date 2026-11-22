import pytest

from app import config, db, payouts, routes
from seed.seed import seed_db


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A seeded temp DB, cache-only Gemini, and the real simulated payout sandbox with every send recorded."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")  # force cache-only
    monkeypatch.setattr(config, "DEMO_COOLDOWN_SECONDS", 0)  # tests reset repeatedly; the throttle has its own test
    routes._demo["last_run"] = None
    seed_db()
    sent = []
    real_send = payouts.send_payout

    def recording_send(conn, ref, destination, amount_paise, note):
        res = real_send(conn, ref, destination, amount_paise, note)
        sent.append({"ref": ref, "destination": destination, "paise": amount_paise, "result": res})
        return res

    monkeypatch.setattr(payouts, "send_payout", recording_send)
    conn = db.connect()
    yield conn, sent
    conn.close()
