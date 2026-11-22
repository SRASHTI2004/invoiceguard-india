# InvoiceGuard India

**An AI accounts-payable agent for Indian businesses that stops fake and wrong GST invoices before any money moves.**
Prototype for Prasunex Innovathon, Round 3. Built from the original InvoiceGuard project and adapted to GST, INR and UPI/bank payouts.

> **Payouts are a simulated sandbox.** No real money moves and no bank or UPI network is contacted. The dashboard labels every payout "SIMULATED SANDBOX". All suppliers, GSTINs, bank accounts and UPI IDs in the demo are fictional.

## The problem

A small Indian business receives supplier invoices as PDFs and pays them by UPI or bank transfer. Three things go wrong:

1. **Fraud**: fake suppliers, duplicate invoices, "our bank details have changed" emails, invoices with hidden text aimed at AI tools.
2. **GST mistakes**: an invalid or made-up GSTIN, IGST charged where CGST+SGST applies (or the reverse), a GST total that does not add up. These cost the buyer input tax credit and create notices later.
3. **Manual checking** that is slow, so mistakes slip through at month end.

## What it does

Upload an invoice PDF. InvoiceGuard India reads it with Gemini, runs it through GST and fraud checks written as plain code, and then **pays it, holds it for a person, or blocks it**, always with a plain-English reason, a per-invoice GST report and an audit-log entry.

- **GST-aware extraction**: supplier and buyer GSTIN, place of supply, HSN/SAC per line, GST rate, taxable value, CGST/SGST/IGST and total.
- **GST checks in code** (see below), shown per invoice as a pass/fail list.
- **INR throughout** with Indian number formatting (`₹1,24,000.00`, lakh and crore groupings on the dashboard).
- **Payouts** to the supplier's *saved* UPI ID or bank account, by UPI, IMPS or RTGS depending on the amount.
- **Idempotent payouts and HOLD-on-failure**: a retry can never pay twice; if a payout fails, the invoice goes back on hold with the reason.
- **AP agent with propose-then-confirm**: ask in plain English ("pay the held invoice from Cedar & Pine"); the agent can only recommend, you confirm with a click, and every check is re-run at that moment.
- **Dashboard**: landing page with a "Try with demo data" button, summary cards, status badges, GST results per invoice, supplier list, audit log, light/dark mode and a phone layout.

## How the GST checks work

All in `backend/app/gst.py`, pure functions with no AI and no network. Each returns pass or fail with a message, and failures are marked **blocks payment** or **needs a person**.

| Check | Rule | If it fails |
|---|---|---|
| Supplier GSTIN | 15 characters in GSTIN format, a valid state code, and the **15th character must equal the mod-36 check character** computed from the first 14 | **Block** (a made-up number) |
| GSTIN matches saved supplier | the GSTIN on the invoice equals the one saved for that supplier | **Block** |
| Buyer GSTIN | the invoice is billed to *our* GSTIN (otherwise we cannot claim input tax credit) | Hold |
| Tax type | supplier state (first two GSTIN digits) vs place of supply: same state requires **CGST + SGST** only, different state requires **IGST** only | Hold |
| HSN / SAC | every line has a 4, 6 or 8 digit code | Hold |
| GST rate | each line uses a valid slab (0, 0.25, 3, 5, 12, 18, 28%) | Hold |
| Taxable value | equals the sum of quantity x unit price over the lines | Hold |
| GST amount | equals the tax implied by each line's own rate (rounded half-up, Rs 1 tolerance) | Hold |
| CGST = SGST | the two halves are equal | Hold |
| Invoice total | taxable value + GST | Hold |

Fraud checks alongside them (`checks.py`): duplicate invoice, purchase-order match, approved-supplier list, **payee check** (a UPI ID or bank account printed on the invoice that differs from the saved one is blocked), per-payment and daily limits. Then Gemini does a separate review for scam signals and hidden instructions.

The decision (`decide.py`) is a small pure function: any block-level finding or high AI risk blocks; any hold-level finding, medium risk or an AI failure holds; otherwise the invoice is auto-paid. **Only that function or an explicit owner click can lead to a payment.**

### Why it is safe against prompt injection
- The AI never pays anything. It returns schema-validated JSON; plain code decides.
- The payee is always the saved UPI ID or account, never one written on the invoice.
- If the AI review is unavailable or malformed, the invoice is held, never auto-paid.
- Clear signals (hidden instructions to an AI) have a minimum risk floor in code, so a model that under-scores them still gets blocked.

## Payouts

`backend/app/payouts.py` is the payout adapter. The only built-in provider is **`simulated`**, a labelled sandbox with a ledger that behaves like a real rail:

- **Destination** comes from the supplier's saved details. UPI up to Rs 1,00,000; above that (or if the supplier prefers bank) IMPS up to Rs 2,00,000, then RTGS. UPI over the limit with no saved bank account is an error and the invoice is held.
- **Idempotent**: the same payout reference always returns the same payout.
- **Failures**: insufficient sandbox funds (`SANDBOX_BALANCE_PAISE`) and a rejected beneficiary (a saved UPI ID or account containing `fail`) both put the invoice back on hold with the reason.

A real provider (for example RazorpayX Payouts or a bank API) would implement the same two functions and be selected with `PAYOUT_PROVIDER`; the pipeline would not change. That integration is not built or tested here.

## Run it

Needs Python 3.12 and Node 20.

```bash
# backend
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env          # GEMINI_API_KEY is optional: the demo data is cached
python -m uvicorn app.main:app --port 8000

# frontend (second terminal): dev server with API proxy, or build once for the backend to serve
cd frontend
npm ci
npm run dev                         # http://localhost:5173
# or: npm run build                 # then open http://localhost:8000
```

Without a `GEMINI_API_KEY` the 13 sample invoices still work instantly because their Gemini results are cached in `backend/seed/gemini_cache.json` (real Gemini output, saved by `python -m seed.export_cache`). **Uploading a new PDF needs a key.** On Render the key is optional for the same reason.

**Deploy**: `render.yaml` defines a Docker web service named `invoiceguard-india` (separate from the original). The free plan has no persistent disk, so SQLite is re-created and re-seeded on every start.

## Demo steps

1. Open the app and click **Try with demo data**. Thirteen invoices are processed in a few seconds.
2. Read the summary cards, then open the Invoices tab. Failed GST checks are expanded in red.
3. Walk through the cases (see [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for a 3-minute flow): fake GSTIN, wrong tax type, wrong GST total, duplicate, changed payee, hidden prompt injection.
4. Open **Approvals** and approve the Cedar & Pine partial delivery, or ask the **AP agent** to propose it and confirm.

## Tests and evaluation

```bash
cd backend
python -m pytest                    # 128 tests: GST, checks, payouts, pipeline, agent, Gemini handling, seed data
python -m eval.run_eval             # uses the cached Gemini results; add --live-gemini to call Gemini
```

Result on the 12 labelled invoices (5 valid, 7 fraud or error cases):

| Measure | Result |
|---|---|
| Fraud and error cases caught | **7 / 7** (duplicate, fake GSTIN, wrong tax type, wrong GST total, changed payee, prompt injection, unapproved supplier) |
| Valid invoices wrongly held | **0 / 5** |
| Fraudulent amount stopped | ₹15,14,498.00 of ₹15,14,498.00 |

"Caught" means not auto-paid. Wrong tax type and wrong GST total are **held** for a person (they can be honest mistakes); the rest are **blocked**. This is a small, hand-built test set, so read it as a demonstration that the checks work, not as a measured production accuracy.

## Project layout

```
backend/app/   gst.py (GST rules)  checks.py (fraud rules)  decide.py  extract.py  ai_review.py
               payouts.py  pipeline.py  agent.py  routes.py  money.py
backend/seed/  data.py (fictional suppliers and invoices)  make_pdfs.py  gemini_cache.json  invoices/
backend/eval/  run_eval.py        backend/tests/
frontend/      React + TypeScript dashboard (Vite)
```

Money is stored as integer paise, never floats. Secrets live in `.env` (git-ignored) and are never logged.
