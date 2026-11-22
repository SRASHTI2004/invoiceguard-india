import pytest

from app import checks, config, db
from seed.data import BUYER, INVOICES, SUP, compute
from seed.seed import seed_db

SUPPLIER = "Mahalaxmi Office Supplies"  # Maharashtra supplier, UPI saved, PO-2001 for Rs 1,77,178.00
UPI = SUP[SUPPLIER]["upi"]


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    seed_db()
    c = db.connect()
    yield c
    c.close()


def good_invoice(**over):
    """The valid Mahalaxmi sample as the extraction dict (IGST: Maharashtra -> Karnataka)."""
    src = INVOICES[0]
    t = compute(src)
    inv = dict(supplier_name=SUPPLIER, supplier_gstin=SUP[SUPPLIER]["gstin"], buyer_gstin=BUYER["gstin"],
               place_of_supply=BUYER["place_of_supply"], invoice_number=src["number"], invoice_date=src["date"],
               due_date=src["due"], po_number="PO-2001", taxable_paise=t["taxable"], cgst_paise=0, sgst_paise=0,
               igst_paise=t["igst"], total_paise=t["total"], payee_upi=UPI, payee_account=None, payee_ifsc=None,
               line_items=[{"description": d, "hsn": h, "qty": q, "unit_paise": u, "gst_rate": r}
                           for d, h, q, u, r in src["items"]])
    inv.update(over)
    return inv


def codes(findings):
    return {f.code for f in findings}


def save(conn, inv, status="RECEIVED", paid_at=None):
    sid = checks.get_supplier(conn, inv["supplier_name"])["id"]
    cur = conn.execute(
        "INSERT INTO invoices (supplier_id, supplier_name, invoice_number, invoice_date, total_paise, status, paid_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (sid, inv["supplier_name"], inv["invoice_number"], inv["invoice_date"], inv["total_paise"], status, paid_at))
    conn.commit()
    return cur.lastrowid


def test_clean_invoice_passes(conn):
    assert checks.run_checks(conn, good_invoice()) == []


def test_report_lists_every_gst_check_with_results(conn):
    findings, report = checks.run_checks_with_report(conn, good_invoice())
    assert findings == [] and report and all(r.ok for r in report)
    labels = {r.label for r in report}
    assert {"Supplier GSTIN", "Buyer GSTIN", "CGST+SGST vs IGST", "HSN / SAC codes", "Taxable value",
            "Invoice total"} <= labels


def test_missing_fields_holds(conn):
    f = checks.run_checks(conn, good_invoice(invoice_number=""))
    assert codes(f) == {"missing_fields"} and f[0].severity == checks.HOLD


def test_missing_payment_details_holds(conn):
    f = checks.run_checks(conn, good_invoice(payee_upi=None))
    assert codes(f) == {"missing_fields"} and "payment details" in f[0].message


def test_unreadable_line_items_hold(conn):
    inv = good_invoice(line_items=[{"description": "x", "hsn": "4802", "qty": None, "unit_paise": 5, "gst_rate": 18}])
    assert codes(checks.run_checks(conn, inv)) == {"bad_line_items"}
    assert codes(checks.run_checks(conn, good_invoice(line_items=[]))) == {"no_line_items"}


def test_gst_failures_become_findings_with_the_right_severity(conn):
    wrong_total = checks.run_checks(conn, good_invoice(total_paise=17717800 + 100000))
    assert "gst_total_wrong" in codes(wrong_total)
    assert [f for f in wrong_total if f.code == "gst_total_wrong"][0].severity == checks.HOLD
    fake = SUP[SUPPLIER]["gstin"][:14] + "A"
    bad = checks.run_checks(conn, good_invoice(supplier_gstin=fake))
    assert [f for f in bad if f.code == "supplier_gstin_invalid"][0].severity == checks.BLOCK


def test_gstin_must_match_the_saved_one(conn):
    other = SUP["Brightline Packaging Pvt Ltd"]["gstin"]  # a valid GSTIN, but not this supplier's
    assert "supplier_gstin_mismatch" in codes(checks.run_checks(conn, good_invoice(supplier_gstin=other)))


def test_wrong_buyer_gstin_holds(conn):
    f = checks.run_checks(conn, good_invoice(buyer_gstin=SUP[SUPPLIER]["gstin"]))
    assert codes(f) == {"buyer_gstin_mismatch"} and f[0].severity == checks.HOLD


def test_unknown_and_unapproved_supplier_block(conn):
    assert "unknown_supplier" in codes(checks.run_checks(conn, good_invoice(supplier_name="Nobody Ltd")))
    f = checks.run_checks(conn, good_invoice(supplier_name="Shadowline Trading", po_number="PO-2001"))
    assert "unapproved_supplier" in codes(f)


def test_duplicate_invoice_number(conn):
    save(conn, good_invoice(invoice_date="2026-01-01", total_paise=5))
    assert "duplicate_number" in codes(checks.run_checks(conn, good_invoice()))


def test_duplicate_amount_and_date(conn):
    save(conn, good_invoice(invoice_number="OTHER"))
    assert "duplicate_amount_date" in codes(checks.run_checks(conn, good_invoice()))


def test_invoice_does_not_duplicate_itself(conn):
    inv = good_invoice()
    iid = save(conn, inv)
    assert checks.run_checks(conn, inv, exclude_id=iid) == []


def test_po_checks(conn):
    # a consistent invoice that is Rs 1,000 more / less than the PO
    def with_total(delta):
        items = [{"description": "x", "hsn": "4802", "qty": 1, "unit_paise": 1000000 + delta, "gst_rate": 0}]
        total = 1000000 + delta
        return good_invoice(line_items=items, taxable_paise=total, igst_paise=0, total_paise=total, cgst_paise=0,
                            sgst_paise=0, invoice_number=f"T{delta}")
    assert "over_po" in codes(checks.run_checks(conn, with_total(20000000)))
    under = checks.run_checks(conn, with_total(0))
    assert "under_po" in codes(under) and [f for f in under if f.code == "under_po"][0].severity == checks.HOLD
    assert "po_not_found" in codes(checks.run_checks(conn, good_invoice(po_number="PO-9999")))
    assert "po_wrong_supplier" in codes(checks.run_checks(conn, good_invoice(po_number="PO-2002")))
    assert codes(checks.run_checks(conn, good_invoice(po_number=None))) == {"no_po"}


def test_changed_upi_blocks_but_case_and_spaces_do_not(conn):
    f = checks.run_checks(conn, good_invoice(payee_upi="thief@ybl"))
    assert codes(f) == {"payee_changed"} and f[0].severity == checks.BLOCK
    assert checks.run_checks(conn, good_invoice(payee_upi=f" {UPI.upper()} ")) == []


def test_changed_bank_account_blocks(conn):
    # Brightline is saved with a bank account; the invoice prints a different one
    sup = SUP["Brightline Packaging Pvt Ltd"]
    inv = good_invoice(supplier_name=sup["name"], supplier_gstin=sup["gstin"], payee_upi=None, po_number="PO-2002",
                       payee_account="111122223333", payee_ifsc=sup["ifsc"])
    assert "payee_changed" in codes(checks.run_checks(conn, inv))
    same = dict(inv, payee_account=sup["account"])
    assert "payee_changed" not in codes(checks.run_checks(conn, same))
    wrong_ifsc = dict(same, payee_ifsc="HDFC0000001")
    assert "payee_changed" in codes(checks.run_checks(conn, wrong_ifsc))


def test_per_payment_limit(conn, monkeypatch):
    monkeypatch.setattr(config, "PER_PAYMENT_LIMIT_PAISE", 100000)
    f = checks.run_checks(conn, good_invoice())
    assert codes(f) == {"over_payment_limit"} and f[0].severity == checks.HOLD


def test_daily_limit_counts_only_todays_paid(conn, monkeypatch):
    monkeypatch.setattr(config, "DAILY_LIMIT_PAISE", 20000000)
    save(conn, good_invoice(invoice_number="A", invoice_date="2026-01-01"), "PAID", "2026-11-06 09:00:00")
    save(conn, good_invoice(invoice_number="B", invoice_date="2026-01-02"), "PAID", "2026-11-05 09:00:00")  # other day
    save(conn, good_invoice(invoice_number="C", invoice_date="2026-01-03"), "HELD")  # not paid
    assert checks.paid_today_paise(conn, "2026-11-06") == 17717800
    assert "over_daily_limit" in codes(checks.run_checks(conn, good_invoice(), today="2026-11-06"))
    assert "over_daily_limit" not in codes(checks.run_checks(conn, good_invoice(), today="2026-11-07"))


def test_money_is_formatted_in_rupees():
    assert checks.money(17717800) == "₹1,77,178.00"
