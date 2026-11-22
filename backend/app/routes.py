import json
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from . import agent, config, db, gemini, gst, payouts, pipeline

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
                "payout_batch_id, payout_status, payout_method, payout_destination, paid_at, created_at")


@router.get("/invoices")
def list_invoices(conn=Depends(get_conn)):
    rows = _rows(conn, f"SELECT {LIST_COLUMNS} FROM invoices ORDER BY id DESC")
    for r in rows:
        r["gst_report"] = json.loads(r["gst_report"]) if r["gst_report"] else []
    return rows


@router.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, conn=Depends(get_conn)):
    inv = pipeline.get_invoice(conn, invoice_id)
    if inv is None:
        raise HTTPException(404, "Invoice not found")
    return inv


@router.post("/invoices/upload")
async def upload_invoice(file: UploadFile = File(...), conn=Depends(get_conn)):
    data = await file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(413, "File is too large (10 MB max)")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Please upload a PDF file")
    return pipeline.process_invoice(conn, data, Path(file.filename or "invoice.pdf").name)


@router.post("/invoices/{invoice_id}/approve")
def approve(invoice_id: int, conn=Depends(get_conn)):
    return _act(pipeline.approve, conn, invoice_id)


@router.post("/invoices/{invoice_id}/reject")
def reject(invoice_id: int, conn=Depends(get_conn)):
    return _act(pipeline.reject, conn, invoice_id)


@router.post("/invoices/{invoice_id}/refresh-payout")
def refresh_payout(invoice_id: int, conn=Depends(get_conn)):
    return _act(pipeline.refresh_payout, conn, invoice_id)


@router.get("/suppliers")
def suppliers(conn=Depends(get_conn)):
    rows = _rows(conn, "SELECT id, name, approved, gstin, bank_account, ifsc, upi_id, payout_method, "
                       "notes AS address FROM suppliers ORDER BY name")
    for r in rows:  # never send a full account number to the browser
        r["bank_account"] = payouts.mask_account(r["bank_account"]) if r["bank_account"] else None
        r["state"] = gst.state_name(gst.state_code_of(r["gstin"]))
    return rows


@router.get("/summary")
def summary(conn=Depends(get_conn)):
    return pipeline.summary(conn)


@router.get("/config")
def public_config():
    """Non-secret settings the dashboard shows (buyer identity, payout mode label)."""
    return {"buyer_name": config.BUYER_NAME, "buyer_gstin": config.BUYER_GSTIN, "payout_provider": config.PAYOUT_PROVIDER,
            "payout_label": payouts.SANDBOX_LABEL, "currency": config.CURRENCY}


@router.get("/audit")
def audit_log(invoice_id: int | None = None, conn=Depends(get_conn)):
    if invoice_id is not None:
        return _rows(conn, "SELECT * FROM audit_log WHERE invoice_id = ? ORDER BY id DESC", (invoice_id,))
    return _rows(conn, "SELECT * FROM audit_log ORDER BY id DESC LIMIT 500")


@router.post("/demo/run-samples")
def run_samples(conn=Depends(get_conn)):
    """Demo helper: RESET all invoices, payouts and the audit log, then push the sample PDFs through the firewall in order.
    Always gives the same result (no leftovers from earlier runs). Payouts are simulated, so this is unlimited by
    default; set DEMO_COOLDOWN_SECONDS to rate-limit it (a repeat call inside the window returns the existing results)."""
    with _demo_lock:  # claim the slot before running so two quick clicks cannot both send payouts
        last = _demo["last_run"]
        recent = last is not None and time.monotonic() - last < config.DEMO_COOLDOWN_SECONDS
        has_data = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] > 0
        if recent and has_data:
            ids = [r["id"] for r in conn.execute("SELECT id FROM invoices ORDER BY id")]
            return {"processed": len(ids), "invoice_ids": ids, "summary": pipeline.summary(conn),
                    "throttled": True, "note": DEMO_NOTE}
        _demo["last_run"] = time.monotonic()
    pipeline.reset_demo_data(conn)
    processed = []
    for pdf in sorted(SAMPLES_DIR.glob("*.pdf")):
        processed.append(pipeline.process_invoice(conn, pdf.read_bytes(), pdf.name)["id"])
    return {"processed": len(processed), "invoice_ids": processed, "summary": pipeline.summary(conn), "throttled": False}


class AgentRequest(BaseModel):
    message: str


class ConfirmRequest(BaseModel):
    invoice_ids: list[int]


@router.post("/agent/confirm")
def confirm_agent_proposal(req: ConfirmRequest, conn=Depends(get_conn)):
    """The owner clicked "Confirm and pay". Each invoice is fully re-checked now, then paid via the approve path."""
    if not req.invoice_ids or len(req.invoice_ids) > 20:
        raise HTTPException(400, "Confirm between 1 and 20 invoices")
    return {"results": [pipeline.confirm_proposal(conn, i) for i in dict.fromkeys(req.invoice_ids)]}


@router.post("/agent")
def run_agent(req: AgentRequest, conn=Depends(get_conn)):
    """AP agent: e.g. "pay all held invoices due this week". It returns a proposal; it never pays."""
    if not req.message.strip():
        raise HTTPException(400, "Please type a request")
    try:
        return agent.run_agent(conn, req.message)
    except gemini.GeminiError as e:
        raise HTTPException(503, f"The AI agent is unavailable right now ({e}). Use the Approvals page instead.")
    except Exception as e:  # network errors, timeouts, anything unexpected: still give the UI a readable message
        raise HTTPException(503, f"The AI agent hit an error ({type(e).__name__}). Use the Approvals page instead.")
