"""Generate the sample GST invoice PDFs (5 different layouts) and labels.json.  Run from backend/:
    python -m seed.make_pdfs
All names, GSTINs, accounts and UPI IDs are fictional.
"""
import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.money import inr
from seed.data import BUYER, DEMO_INVOICES, INVOICES, SUP, compute

OUT = Path(__file__).parent / "invoices"
W, H = A4


def rs(paise: int) -> str:
    """PDF standard fonts have no rupee glyph, so invoices print 'Rs.' (as many real invoices do)."""
    return inr(paise).replace("₹", "Rs. ")


def wrap(text: str, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return lines + [cur]


def sup_of(inv) -> dict:
    return SUP[inv["supplier"]]


def gstin_of(inv) -> str:
    return inv.get("gstin") or sup_of(inv)["gstin"]


def pay_details(inv) -> dict:
    """What the invoice PRINTS as the payment destination (the changed-payee sample overrides it)."""
    s = sup_of(inv)
    d = inv.get("pay") or {"upi": s["upi"], "account": s["account"], "ifsc": s["ifsc"]}
    if not inv.get("pay") and s["method"] == "UPI":
        return {"upi": d["upi"], "account": None, "ifsc": None}
    return d


def pay_lines(inv) -> list[str]:
    d = pay_details(inv)
    out = []
    if d.get("upi"):
        out.append(f"UPI ID: {d['upi']}")
    if d.get("account"):
        out.append(f"Bank A/c No: {d['account']}   IFSC: {d['ifsc']}")
    return out


def table(c, inv, x, y, widths, font="Helvetica", size=9, zebra=None, line=True):
    """Line items with HSN/SAC and GST rate, then the tax summary. Returns y after the summary."""
    bold = {"Courier": "Courier-Bold", "Times": "Times-Bold"}.get(font, font + "-Bold")
    regular = "Times-Roman" if font == "Times" else font
    cols = [x]
    for w in widths[:-1]:
        cols.append(cols[-1] + w)
    right = x + sum(widths)
    c.setFont(bold, size)
    for cx, label in zip(cols, ["Description", "HSN/SAC", "Qty", "Rate (Rs.)", "GST %", "Taxable (Rs.)"]):
        c.drawString(cx, y, label)
    y -= 6
    if line:
        c.line(x, y, right, y)
    y -= 15
    for i, (desc, hsn, qty, unit, rate) in enumerate(inv["items"]):
        if zebra and i % 2 == 0:
            c.setFillColorRGB(*zebra)
            c.rect(x - 4, y - 4, sum(widths) + 8, 16, stroke=0, fill=1)
            c.setFillColorRGB(0, 0, 0)
        c.setFont(regular, size)
        c.drawString(cols[0], y, desc[: int(widths[0] / (size * 0.5))])
        c.drawString(cols[1], y, hsn)
        c.drawString(cols[2], y, str(qty))
        c.drawString(cols[3], y, inr(unit).replace("₹", ""))
        c.drawString(cols[4], y, f"{rate:g}%")
        c.drawRightString(right, y, inr(qty * unit).replace("₹", ""))
        y -= 17
    if line:
        c.line(x, y + 8, right, y + 8)
    t = compute(inv)
    y -= 6
    rows = [("Taxable value", t["taxable"])]
    if t["cgst"] or t["sgst"]:
        rows += [("CGST", t["cgst"]), ("SGST", t["sgst"])]
    if t["igst"]:
        rows += [("IGST", t["igst"])]
    for label, amount in rows:
        c.setFont(regular, size)
        c.drawString(cols[3] - 20, y, label)
        c.drawRightString(right, y, rs(amount))
        y -= 15
    c.setFont(bold, size + 2)
    c.drawString(cols[3] - 20, y, "TOTAL")
    c.drawRightString(right, y, rs(t["total"]))
    return y - 30


def gst_block(c, inv, x, y, size=9, font="Helvetica"):
    """Supplier GSTIN, buyer, place of supply. Returns the y after it."""
    c.setFont(font, size)
    for t in [f"Supplier GSTIN: {gstin_of(inv)}", f"Bill to: {BUYER['name']}", f"Buyer GSTIN: {BUYER['gstin']}",
              f"Place of supply: {BUYER['place_of_supply']}"]:
        c.drawString(x, y, t)
        y -= size + 4
    return y


def payment_block(c, inv, x, y, font="Helvetica", size=9, chars=70):
    c.setFont(font, size)
    c.drawString(x, y, "Payment terms: net 15 days. Pay to:")
    for ln in pay_lines(inv):
        y -= size + 4
        c.drawString(x, y, ln)
    return y


def banner(c, inv, x, y, width_chars=80, color=(0.8, 0, 0)):
    if not inv.get("banner"):
        return y
    c.setFillColorRGB(*color)
    c.setFont("Helvetica-Bold", 10)
    for ln in wrap(inv["banner"], width_chars):
        c.drawString(x, y, ln)
        y -= 13
    c.setFillColorRGB(0, 0, 0)
    return y - 6


def hidden_text(c, inv):
    """White 1pt text at the bottom of the page: invisible to a human, readable by a text extractor."""
    if inv.get("hidden"):
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica", 1)
        c.drawString(40, 30, inv["hidden"])
        c.setFillColorRGB(0, 0, 0)


def style_classic(c, inv):
    s = sup_of(inv)
    c.setFont("Helvetica-Bold", 19)
    c.drawString(40, H - 55, s["name"])
    c.setFont("Helvetica", 9)
    for i, ln in enumerate(wrap(s["address"], 70)):
        c.drawString(40, H - 70 - i * 11, ln)
    c.setFont("Helvetica-Bold", 22)
    c.setFillColorRGB(*inv["accent"])
    c.drawRightString(W - 40, H - 55, "TAX INVOICE")
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica", 10)
    for i, t in enumerate([f"Invoice No: {inv['number']}", f"Date: {inv['date']}", f"Due: {inv['due']}", f"PO Ref: {inv['po']}"]):
        c.drawRightString(W - 40, H - 76 - i * 13, t)
    y = gst_block(c, inv, 40, H - 125)
    y = banner(c, inv, 40, y - 10)
    y = table(c, inv, 40, min(y, H - 200) - 10, [210, 55, 35, 75, 45, 90])
    payment_block(c, inv, 40, y)
    hidden_text(c, inv)


def style_modern(c, inv):
    s = sup_of(inv)
    c.setFillColorRGB(*inv["accent"])
    c.rect(0, H - 105, W, 105, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(40, H - 55, s["name"])
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 72, s["address"][:90])
    c.drawString(40, H - 86, f"GSTIN: {gstin_of(inv)}")
    c.setFillColorRGB(0.94, 0.94, 0.94)
    c.rect(40, H - 175, W - 80, 50, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 9)
    for i, (k, v) in enumerate([("TAX INVOICE #", inv["number"]), ("ISSUED", inv["date"]), ("DUE", inv["due"]), ("PURCHASE ORDER", inv["po"])]):
        c.drawString(55 + i * 125, H - 143, k)
        c.setFont("Helvetica", 10)
        c.drawString(55 + i * 125, H - 158, v)
        c.setFont("Helvetica-Bold", 9)
    c.setFont("Helvetica", 9)
    c.drawString(40, H - 195, f"Billed to {BUYER['name']}   |   Buyer GSTIN: {BUYER['gstin']}")
    c.drawString(40, H - 208, f"Place of supply: {BUYER['place_of_supply']}")
    y = banner(c, inv, 40, H - 232)
    y = table(c, inv, 40, min(y, H - 245), [205, 55, 35, 75, 45, 95], zebra=(0.95, 0.97, 1), line=False)
    payment_block(c, inv, 40, y)
    hidden_text(c, inv)


def style_minimal(c, inv):
    s = sup_of(inv)
    y = H - 55
    c.setFont("Courier-Bold", 13)
    c.drawString(40, y, s["name"].upper())
    c.setFont("Courier", 9)
    for t in [s["address"][:78], f"GSTIN {gstin_of(inv)}", "-" * 66,
              f"TAX INVOICE {inv['number']}   DATE {inv['date']}   DUE {inv['due']}",
              f"ORDER REF {inv['po']}", f"CUSTOMER: {BUYER['name']}  GSTIN {BUYER['gstin']}",
              f"PLACE OF SUPPLY: {BUYER['place_of_supply']}", "-" * 66]:
        y -= 14
        c.drawString(40, y, t)
    y = banner(c, inv, 40, y - 18, 70, (0, 0, 0))
    y = table(c, inv, 40, y - 10, [205, 60, 35, 75, 45, 90], font="Courier", size=8, line=False)
    payment_block(c, inv, 40, y, font="Courier")
    hidden_text(c, inv)


def style_sidebar(c, inv):
    s = sup_of(inv)
    c.setFillColorRGB(*inv["accent"])
    c.rect(0, 0, 170, H, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 14)
    for i, ln in enumerate(wrap(s["name"], 16)):
        c.drawString(20, H - 60 - i * 18, ln)
    c.setFont("Helvetica", 8)
    for i, ln in enumerate(wrap(s["address"], 30)):
        c.drawString(20, H - 135 - i * 11, ln)
    c.drawString(20, H - 205, "GSTIN:")
    c.drawString(20, H - 217, gstin_of(inv))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20, 160, "PAYMENT DETAILS")
    c.setFont("Helvetica", 8)
    y = 146
    for ln in pay_lines(inv):
        for part in wrap(ln, 30):
            c.drawString(20, y, part)
            y -= 11
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 21)
    c.drawString(200, H - 55, "Tax Invoice")
    c.setFont("Helvetica", 9)
    for i, t in enumerate([f"Number: {inv['number']}", f"Date: {inv['date']}   Due: {inv['due']}", f"Your PO: {inv['po']}",
                           f"To: {BUYER['name']}", f"Buyer GSTIN: {BUYER['gstin']}", f"Place of supply: {BUYER['place_of_supply']}"]):
        c.drawString(200, H - 82 - i * 13, t)
    y = banner(c, inv, 200, H - 175, 55)
    table(c, inv, 200, min(y, H - 190), [120, 45, 25, 60, 35, 65], size=7.5)
    hidden_text(c, inv)


def style_statement(c, inv):
    s = sup_of(inv)
    c.setFont("Times-Bold", 21)
    c.drawCentredString(W / 2, H - 50, s["name"])
    c.setFont("Times-Italic", 10)
    c.drawCentredString(W / 2, H - 64, s["address"])
    c.drawCentredString(W / 2, H - 77, f"GSTIN {gstin_of(inv)}")
    c.rect(40, H - 160, W - 80, 62)
    c.setFont("Times-Bold", 12)
    c.drawString(50, H - 114, f"TAX INVOICE  {inv['number']}")
    c.setFont("Times-Roman", 10.5)
    c.drawString(50, H - 129, f"Issued {inv['date']}  |  Payment due {inv['due']}  |  Order {inv['po']}")
    c.drawString(50, H - 143, f"Customer: {BUYER['name']}  (GSTIN {BUYER['gstin']})  |  Place of supply: {BUYER['place_of_supply']}")
    y = banner(c, inv, 40, H - 182, 78, inv["accent"])
    y = table(c, inv, 40, min(y, H - 195), [210, 55, 35, 75, 45, 90], font="Times", size=10)
    payment_block(c, inv, 40, y, font="Times-Roman", size=10)
    hidden_text(c, inv)


STYLES = dict(classic=style_classic, modern=style_modern, minimal=style_minimal,
              sidebar=style_sidebar, statement=style_statement)


def main(only=None):
    OUT.mkdir(exist_ok=True)
    labels = []
    for inv in INVOICES + DEMO_INVOICES:
        if inv in INVOICES:  # demo-only invoices are not part of the eval labels
            labels.append({k: inv[k] for k in ("file", "supplier", "number", "is_fraud", "expected", "category")})
        if only and inv["file"] not in only:
            continue
        c = canvas.Canvas(str(OUT / inv["file"]), pagesize=A4, invariant=1)  # invariant: same bytes every run
        c.setTitle(f"Tax Invoice {inv['number']}")
        STYLES[inv["style"]](c, inv)
        c.save()
    (Path(__file__).parent / "labels.json").write_text(json.dumps(labels, indent=2))
    print(f"wrote {len(INVOICES) + len(DEMO_INVOICES)} PDFs to {OUT}")


if __name__ == "__main__":
    main(only=sys.argv[1:] or None)  # optional: file names to regenerate
