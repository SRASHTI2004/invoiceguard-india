import csv
import io

from fastapi.testclient import TestClient

from app import exports
from app.main import app
from seed.data import INVOICES, compute
from tests.test_pipeline import run


def parse(text):
    assert text.startswith("﻿") is False  # the BOM is added by the endpoint, not by tally_csv
    return list(csv.reader(io.StringIO(text)))


def test_columns_and_one_row_per_paid_invoice(env):
    conn, _ = env
    for i in INVOICES:
        run(conn, i["file"])  # 5 paid, the rest blocked or held
    rows = parse(exports.tally_csv(conn))
    assert rows[0] == ["Date", "Supplier", "Supplier GSTIN", "Invoice No", "Taxable Value", "CGST", "SGST", "IGST", "Total",
                       "Payment Reference"]
    assert len(rows) == 1 + 5
    # saved supplier names (the PDF for Konkan prints its name in capitals)
    assert {r[1] for r in rows[1:]} == {"Mahalaxmi Office Supplies", "Brightline Packaging Pvt Ltd", "Konkan Freight Logistics",
                                        "Summit IT Services Pvt Ltd", "GreenLeaf Facility Services"}  # nothing blocked or held


def test_values_are_accountant_friendly(env):
    conn, _ = env
    run(conn, "inv01_mahalaxmi.pdf")
    run(conn, "inv02_brightline.pdf")
    rows = parse(exports.tally_csv(conn))[1:]
    by = {r[3]: r for r in rows}
    igst = by["MOS/26-27/1041"]  # Maharashtra -> Karnataka: IGST
    assert igst[0] == "28-10-2026" and igst[2].startswith("27") and len(igst[2]) == 15
    assert igst[4:9] == ["153100.00", "0.00", "0.00", "24078.00", "177178.00"]  # plain numbers: no symbol, no commas
    assert igst[9].startswith("SIM-ig-")
    cs = by["BP/26-27/8821"]  # Karnataka -> Karnataka: CGST + SGST
    assert cs[4:9] == ["40250.00", "3514.50", "3514.50", "0.00", "47279.00"]
    t = compute(INVOICES[1])
    assert float(cs[4]) + float(cs[5]) + float(cs[6]) + float(cs[7]) == t["total"] / 100  # components add up to the total


def test_rows_are_sorted_by_invoice_date(env):
    conn, _ = env
    for f in ("inv05_greenleaf.pdf", "inv02_brightline.pdf", "inv01_mahalaxmi.pdf"):
        run(conn, f)
    dates = [r[0] for r in parse(exports.tally_csv(conn))[1:]]
    keys = [d[6:] + d[3:5] + d[:2] for d in dates]
    assert keys == sorted(keys)


def test_empty_export_is_just_the_header(env):
    conn, _ = env
    assert len(parse(exports.tally_csv(conn))) == 1


def test_formula_injection_is_neutralised():
    assert exports.safe("=HYPERLINK(\"http://evil\")") == "'=HYPERLINK(\"http://evil\")"
    for bad in ("+1+1", "-2", "@SUM(A1)", "\t=cmd", "=cmd"):
        assert exports.safe(bad).startswith("'")
    assert exports.safe("Normal & Co. Pvt Ltd") == "Normal & Co. Pvt Ltd"
    assert exports.safe("a\nb") == "a b" and exports.safe(None) == ""


def test_endpoint_downloads_a_csv_with_bom(env):
    conn, _ = env
    run(conn, "inv01_mahalaxmi.pdf")
    run(conn, "inv08_pinnacle_wrong_tax_type.pdf")  # held: must not appear
    with TestClient(app) as c:
        r = c.get("/api/export/tally.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"] and ".csv" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM so Excel reads it right
    text = r.content.decode("utf-8-sig")
    assert "MOS/26-27/1041" in text and "PP/2217" not in text and text.count("\r\n") == 2
