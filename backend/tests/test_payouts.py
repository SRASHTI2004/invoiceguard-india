import pytest

from app import config, db, payouts
from seed.seed import seed_db


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    seed_db()
    c = db.connect()
    yield c
    c.close()


def supplier(**over):
    s = {"upi_id": "ravi.kumar@okhdfcbank", "bank_account": "50200034871265", "ifsc": "HDFC0000240",
         "payout_method": "UPI"}
    s.update(over)
    return s


def test_upi_is_used_when_preferred_and_within_the_limit():
    d = payouts.destination_for(supplier(), 5000000)
    assert d["method"] == "UPI" and d["upi_id"] == "ravi.kumar@okhdfcbank" and d["masked"] == "ra***@okhdfcbank"


def test_amount_over_the_upi_limit_falls_back_to_the_bank_account():
    d = payouts.destination_for(supplier(), payouts.UPI_LIMIT_PAISE + 1)
    assert d["method"] == "IMPS" and d["account"] == "50200034871265" and d["masked"] == "XXXXXXXXXX1265"


def test_large_bank_payments_use_rtgs():
    assert payouts.destination_for(supplier(payout_method="BANK"), payouts.IMPS_LIMIT_PAISE)["method"] == "IMPS"
    assert payouts.destination_for(supplier(payout_method="BANK"), payouts.IMPS_LIMIT_PAISE + 1)["method"] == "RTGS"


def test_over_the_upi_limit_without_a_bank_account_is_an_error():
    with pytest.raises(payouts.PayoutError) as e:
        payouts.destination_for(supplier(bank_account=None, ifsc=None), payouts.UPI_LIMIT_PAISE + 1)
    assert e.value.code == "UPI_LIMIT"


def test_no_saved_destination_is_an_error():
    with pytest.raises(payouts.PayoutError) as e:
        payouts.destination_for(supplier(upi_id=None, bank_account=None, ifsc=None, payout_method="BANK"), 100)
    assert e.value.code == "NO_DESTINATION"


def test_masking_never_shows_the_full_account_number():
    assert payouts.mask_account("123456789012") == "XXXXXXXX9012"
    assert "123456789012"[:8] not in payouts.mask_account("123456789012")


def test_payout_is_idempotent_on_ref(conn):
    d = payouts.destination_for(supplier(), 100000)
    first = payouts.send_payout(conn, "ig-1-abcd", d, 100000, "n")
    again = payouts.send_payout(conn, "ig-1-abcd", d, 100000, "n")
    assert first == again and first["status"] == "PENDING" and first["sandbox"] is True
    assert conn.execute("SELECT COUNT(*), SUM(amount_paise) FROM payouts").fetchone()[:] == (1, 100000)  # paid once


def test_different_refs_are_different_payouts(conn):
    d = payouts.destination_for(supplier(), 100000)
    a = payouts.send_payout(conn, "ig-1-a", d, 100000, "n")
    b = payouts.send_payout(conn, "ig-2-b", d, 100000, "n")
    assert a["batch_id"] != b["batch_id"]


def test_insufficient_sandbox_funds(conn, monkeypatch):
    monkeypatch.setattr(config, "SANDBOX_BALANCE_PAISE", 150000)
    d = payouts.destination_for(supplier(), 100000)
    payouts.send_payout(conn, "r1", d, 100000, "n")
    with pytest.raises(payouts.PayoutError) as e:
        payouts.send_payout(conn, "r2", d, 100000, "n")
    assert e.value.code == "INSUFFICIENT_FUNDS"
    assert conn.execute("SELECT COUNT(*) FROM payouts").fetchone()[0] == 1  # the failed one left no record


def test_rejected_beneficiary_sandbox_case(conn):
    d = payouts.destination_for(supplier(upi_id="fail.test@okaxis"), 100000)
    with pytest.raises(payouts.PayoutError) as e:
        payouts.send_payout(conn, "r1", d, 100000, "n")
    assert e.value.code == "BENEFICIARY_REJECTED"


def test_unknown_provider_is_refused(conn, monkeypatch):
    monkeypatch.setattr(config, "PAYOUT_PROVIDER", "razorpayx")
    with pytest.raises(payouts.PayoutError) as e:
        payouts.send_payout(conn, "r1", payouts.destination_for(supplier(), 100), 100, "n")
    assert e.value.code == "NO_PROVIDER"


def test_status_settles_from_pending_to_success(conn):
    d = payouts.destination_for(supplier(), 100000)
    res = payouts.send_payout(conn, "r1", d, 100000, "n")
    assert payouts.get_payout_status(conn, res["batch_id"]) == "SUCCESS"
    assert payouts.get_payout_status(conn, res["batch_id"]) == "SUCCESS"
    with pytest.raises(payouts.PayoutError):
        payouts.get_payout_status(conn, "SIM-unknown")


def test_sandbox_is_clearly_labelled():
    assert "SIMULATED" in payouts.SANDBOX_LABEL and "no real money" in payouts.SANDBOX_LABEL
