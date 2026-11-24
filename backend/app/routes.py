import json
import threading
from datetime import timedelta
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from seed.data import ACCEPTED_AGO, DEFAULT_ACCEPTED_AGO, DEMO_RUNS, UPLOAD_SAMPLES, UPLOAD_SAMPLES2

from . import agent, businesses, config, corrections, db, exports, gemini, gst, msme, payouts, pipeline, timeline, timeutil

router = APIRouter(prefix="/api")
MAX_PDF_BYTES = 10 * 1024 * 1024
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "seed" / "invoices"


_demo = {"last_run": None}  # monotonic time of the last demo run; in memory (a restart also resets the data)
_demo_lock = threading.Lock()
DEMO_NOTE = "Demo data was loaded recently; showing the latest run."


def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def get_business(request: Request, business: int | None = None, conn=Depends(get_conn)) -> int:
    """Which client business this request is for: the X-Business-Id header (or ?business=). Default: business 1."""
    raw = request.headers.get("x-business-id") or business
    try:
        bid = int(raw) if raw not in (None, "") else businesses.DEFAULT_ID
    except ValueError:
        raise HTTPException(400, "Invalid business")
    if businesses.get(conn, bid) is None:
        raise HTTPException(404, "Unknown business")
    return bid


def _own(conn, invoice_id: int, bid: int) -> None:
    """An invoice of another client business does not exist as far as this business is concerned."""
    row = conn.execute("SELECT business_id FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if row is not None and row["business_id"] != bid:
        raise HTTPException(404, "Invoice not found")


def _rows(conn, sql, args=()):
    return [dict(r) for r in conn.execute(sql, args)]


def _act(fn, *args):
    try:
        return fn(*args)
    except pipeline.ActionError as e:
        raise HTTPException(400, str(e))


LIST_COLUMNS = ("id, filename, supplier_name, supplier_gstin, buyer_gstin, place_of_supply, invoice_number, "
                "invoice_date, due_date, po_number, taxable_paise, cgst_paise, sgst_paise, igst_paise, total_paise, "
                "payee_upi, payee_account, payee_ifsc, gst_report, status, decision, reason, risk_score, "
                "payout_batch_id, payout_status, payout_method, payout_destination, paid_at, accepted_date, supplier_id, created_at")


@router.get("/businesses")
def list_businesses(conn=Depends(get_conn)):
    """The client businesses a CA firm can switch between (not scoped: it is the list to choose from)."""
    return businesses.all_with_counts(conn)


@router.get("/invoices")
def list_invoices(conn=Depends(get_conn), bid: int = Depends(get_business)):
    rows = _rows(conn, f"SELECT {LIST_COLUMNS} FROM invoices WHERE business_id = ? ORDER BY id DESC", (bid,))
    asked = {r["invoice_id"]: r["at"] for r in conn.execute(
        "SELECT invoice_id, MAX(created_at) AS at FROM audit_log WHERE event='correction_requested' GROUP BY invoice_id")}
    suppliers = {s["id"]: s for s in conn.execute("SELECT * FROM suppliers")}
    for r in rows:
        r["gst_report"] = json.loads(r["gst_report"]) if r["gst_report"] else []
        r["correction_requested_at"] = asked.get(r["id"])
        # the MSME timer only matters while the invoice is still unpaid
        r["msme"] = msme.deadline(suppliers.get(r["supplier_id"]), r["accepted_date"]) if r["status"] == "HELD" else None
    return rows


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, conn=Depends(get_conn), bid: int = Depends(get_business)):
    _own(conn, invoice_id, bid)
    inv = pipeline.get_invoice(conn, invoice_id)
    if inv is None:
        raise HTTPException(404, "Invoice not found")
    return inv


@router.get("/invoices/{invoice_id}/timeline")
def invoice_timeline(invoice_id: int, conn=Depends(get_conn), bid: int = Depends(get_business)):
    _own(conn, invoice_id, bid)
    t = timeline.build(conn, invoice_id)
    if t is None:
        raise HTTPException(404, "Invoice not found")
    return t


@router.post("/invoices/upload")
async def upload_invoice(file: UploadFile = File(...), conn=Depends(get_conn), bid: int = Depends(get_business)):
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, "File is too large (10 MB max)")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Please upload a PDF file")
    return pipeline.process_invoice(conn, data, Path(file.filename or "invoice.pdf").name, business_id=bid)


class ApproveRequest(BaseModel):
    reason: str | None = None  # required when the invoice still has a GST problem


@router.post("/invoices/{invoice_id}/approve")
def approve(invoice_id: int, req: ApproveRequest | None = None, conn=Depends(get_conn), bid: int = Depends(get_business)):
    _own(conn, invoice_id, bid)
    return _act(pipeline.approve, conn, invoice_id, None, req.reason if req else None)


@router.post("/invoices/{invoice_id}/request-correction")
def request_correction(invoice_id: int, conn=Depends(get_conn), bid: int = Depends(get_business)):
    """Draft (and log) an email asking the supplier for a corrected invoice. Nothing is sent."""
    _own(conn, invoice_id, bid)
    return _act(corrections.draft, conn, invoice_id)


@router.post("/invoices/{invoice_id}/reject")
def reject(invoice_id: int, conn=Depends(get_conn), bid: int = Depends(get_business)):
    _own(conn, invoice_id, bid)
    return _act(pipeline.reject, conn, invoice_id)


@router.post("/invoices/{invoice_id}/refresh-payout")
def refresh_payout(invoice_id: int, conn=Depends(get_conn), bid: int = Depends(get_business)):
    _own(conn, invoice_id, bid)
    return _act(pipeline.refresh_payout, conn, invoice_id)


@router.get("/suppliers")
def suppliers(conn=Depends(get_conn), bid: int = Depends(get_business)):
    rows = _rows(conn, "SELECT id, name, approved, gstin, bank_account, ifsc, upi_id, payout_method, "
                       "notes AS address, msme, msme_written_agreement FROM suppliers WHERE business_id = ? ORDER BY name",
                 (bid,))
    for r in rows:  # never send a full account number to the browser
        r["bank_account"] = payouts.mask_account(r["bank_account"]) if r["bank_account"] else None
        r["state"] = gst.state_name(gst.state_code_of(r["gstin"]))
    return rows


@router.get("/summary")
def summary(conn=Depends(get_conn), bid: int = Depends(get_business)):
    return pipeline.summary(conn, bid)


@router.get("/config")
def public_config(conn=Depends(get_conn), bid: int = Depends(get_business)):
    """Non-secret settings the dashboard shows (the current business, payout mode label)."""
    b = businesses.get(conn, bid)
    return {"business_id": bid, "buyer_name": b["name"], "short_name": b["short_name"], "buyer_gstin": b["gstin"],
            "payout_provider": config.PAYOUT_PROVIDER, "payout_label": payouts.SANDBOX_LABEL, "currency": config.CURRENCY}


@router.get("/audit")
def audit_log(invoice_id: int | None = None, conn=Depends(get_conn), bid: int = Depends(get_business)):
    mine = "invoice_id IN (SELECT id FROM invoices WHERE business_id = ?)"
    if invoice_id is not None:
        return _rows(conn, f"SELECT * FROM audit_log WHERE invoice_id = ? AND {mine} ORDER BY id DESC", (invoice_id, bid))
    return _rows(conn, f"SELECT * FROM audit_log WHERE {mine} ORDER BY id DESC LIMIT 500", (bid,))


UPLOAD_SAMPLES_DIR = Path(__file__).resolve().parents[1] / "seed" / "upload_samples"


@router.get("/samples")
def list_samples(bid: int = Depends(get_business)):
    """Sample invoice PDFs for the current business that the visitor can download and upload to try the whole flow."""
    return [{"file": s["file"], "title": s["title"], "description": s["blurb"], "expected": s["expect"],
             "supplier": s["supplier"], "invoice_number": s["number"], "url": f"/api/samples/{s['file']}"}
            for s in UPLOAD_SAMPLES + UPLOAD_SAMPLES2 if s.get("business", 1) == bid]


@router.get("/samples/{filename}")
def download_sample(filename: str):
    if filename not in {s["file"] for s in UPLOAD_SAMPLES + UPLOAD_SAMPLES2}:  # whitelist: no path tricks
        raise HTTPException(404, "Sample not found")
    return FileResponse(UPLOAD_SAMPLES_DIR / filename, media_type="application/pdf", filename=filename)


@router.get("/export/tally.csv")
def export_tally(conn=Depends(get_conn), bid: int = Depends(get_business)):
    """This business's paid invoices as a CSV for an accountant (Tally-friendly columns)."""
    stamp = timeutil.today_ist().isoformat()
    short = businesses.slug(businesses.get(conn, bid)["short_name"])
    return Response(content="\ufeff" + exports.tally_csv(conn, bid), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="paid-invoices-tally-{short}-{stamp}.csv"'})


@router.get("/evaluation")
def evaluation():
    """Results of the evaluation on the labelled invoice set, as written by `python -m eval.run_eval --write`."""
    f = Path(__file__).resolve().parents[1] / "eval" / "results.json"
    if not f.exists():
        return {"available": False}
    return {"available": True, **json.loads(f.read_text(encoding="utf-8"))}


@router.post("/demo/run-samples")
def run_samples(conn=Depends(get_conn), bid: int = Depends(get_business)):
    """Demo helper: RESET all invoices, payouts and the audit log (every client business), then push each business's sample PDFs through the firewall in order.
    Always gives the same result (no leftovers from earlier runs). Payouts are simulated, so this is unlimited by
    default; set DEMO_COOLDOWN_SECONDS to rate-limit it (a repeat call inside the window returns the existing results)."""
    with _demo_lock:  # claim the slot before running so two quick clicks cannot both send payouts
        last = _demo["last_run"]
        recent = last is not None and time.monotonic() - last < config.DEMO_COOLDOWN_SECONDS
        has_data = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] > 0
        if recent and has_data:
            ids = [r["id"] for r in conn.execute("SELECT id FROM invoices ORDER BY id")]
            return {"processed": len(ids), "invoice_ids": ids, "summary": pipeline.summary(conn, bid),
                    "throttled": True, "note": DEMO_NOTE}
        _demo["last_run"] = time.monotonic()
    pipeline.reset_demo_data(conn)
    processed = []
    today = timeutil.today_ist()
    for biz, sample in DEMO_RUNS:  # in a fixed order, so the result is the same every time
        pdf = SAMPLES_DIR / sample["file"]
        accepted = today - timedelta(days=ACCEPTED_AGO.get(pdf.name, DEFAULT_ACCEPTED_AGO))
        processed.append(pipeline.process_invoice(conn, pdf.read_bytes(), pdf.name, accepted_date=accepted.isoformat(),
                                                  business_id=biz)["id"])
    return {"processed": len(processed), "invoice_ids": processed, "summary": pipeline.summary(conn, bid), "throttled": False}


class AgentRequest(BaseModel):
    message: str


class ConfirmRequest(BaseModel):
    invoice_ids: list[int]


@router.post("/agent/confirm")
def confirm_agent_proposal(req: ConfirmRequest, conn=Depends(get_conn), bid: int = Depends(get_business)):
    """The owner clicked "Confirm and pay". Each invoice is fully re-checked now, then paid via the approve path."""
    if not req.invoice_ids or len(req.invoice_ids) > 20:
        raise HTTPException(400, "Confirm between 1 and 20 invoices")
    def mine(i: int) -> bool:
        row = conn.execute("SELECT business_id FROM invoices WHERE id = ?", (i,)).fetchone()
        return row is None or row["business_id"] == bid
    return {"results": [pipeline.confirm_proposal(conn, i) if mine(i)
                        else {"invoice_id": i, "paid": False, "message": "Invoice not found"}
                        for i in dict.fromkeys(req.invoice_ids)]}


@router.get("/agent/suggestions")
def agent_suggestions(bid: int = Depends(get_business)):
    """The suggested prompts for the current business (these have recorded instant answers)."""
    return {"suggestions": agent.SUGGESTIONS.get(bid, agent.SUGGESTIONS[1])}


@router.post("/agent")
def run_agent(req: AgentRequest, conn=Depends(get_conn), bid: int = Depends(get_business)):
    """AP agent: e.g. "pay all held invoices due this week". It returns a proposal; it never pays."""
    if not req.message.strip():
        raise HTTPException(400, "Please type a request")
    try:
        return agent.run_agent(conn, req.message, business_id=bid)
    except gemini.GeminiError as e:
        raise HTTPException(503, f"The AI agent is unavailable right now ({e}). Use the Approvals page instead.")
    except Exception as e:  # network errors, timeouts, anything unexpected: still give the UI a readable message
        raise HTTPException(503, f"The AI agent hit an error ({type(e).__name__}). Use the Approvals page instead.")
