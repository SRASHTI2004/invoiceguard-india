# InvoiceGuard India

**An AI accounts-payable agent for Indian businesses that stops fake and wrong GST invoices before any money moves.**
Prototype for Prasunex Innovathon, Round 3. Built from the original InvoiceGuard project and adapted to GST, INR, UPI/bank payouts, input tax credit, the MSME 43B(h) payment rule, and CA firms that manage several client businesses.

> **Payouts are a simulated sandbox.** No real money moves and no bank or UPI network is contacted. The dashboard labels every payout "SIMULATED SANDBOX". All suppliers, GSTINs, bank accounts and UPI IDs in the demo are fictional. The MSME timer is guidance, not tax advice.

**Live demo:** <https://invoiceguard-india.onrender.com> (free plan: the first load can take about a minute to wake up; open it and click **Try with demo data**).

## Screenshots

Light theme by default (with a dark mode), desktop at 1440px and phone at 390px. Captured from the running app with a real browser.

| | |
|---|---|
| ![Landing page](docs/screenshots/desktop-01-landing.png) **Landing** | ![Dashboard](docs/screenshots/desktop-02-dashboard.png) **Dashboard**: KPIs, ITC protected, money protected over time, needs your attention |
| ![Invoices](docs/screenshots/desktop-03-invoices.png) **Invoices**: search, status chips, GST badges | ![Invoice drawer with GST failure](docs/screenshots/desktop-04-drawer-gst-fail.png) **Invoice drawer**: six-step journey, wrong tax type held |
| ![Approvals with MSME timers](docs/screenshots/desktop-07-approvals.png) **Approvals**: why each is held, MSME pay-by timers | ![MSME timer in the drawer](docs/screenshots/desktop-17-drawer-msme.png) **MSME timer** (Section 43B(h)) in the invoice drawer |
| ![Corrected invoice email](docs/screenshots/desktop-14-correction-draft.png) **Ask supplier for a corrected invoice**: drafted email naming the exact GST issue | ![Approve with a reason](docs/screenshots/desktop-15-approve-reason.png) **Approve despite a GST problem** needs a reason, saved in the audit log |
| ![Sample invoices to download](docs/screenshots/desktop-16-sample-menu.png) **Download a sample invoice** and upload it yourself | ![AP Agent](docs/screenshots/desktop-11-agent-proposal.png) **AP Agent**: instant answer, tools used, proposal with Confirm |
| ![Prompt injection blocked](docs/screenshots/desktop-06-drawer-injection.png) **Hidden prompt injection** stopped at the AI review | ![Suppliers](docs/screenshots/desktop-08-suppliers.png) **Suppliers**: saved GSTIN, payout details, MSME class |
| ![Audit log](docs/screenshots/desktop-09-audit.png) **Audit log** (IST) | ![Dark mode](docs/screenshots/desktop-12-dark-dashboard.png) **Dark mode** |
| ![Second client business](docs/screenshots/desktop-31-dashboard-kaveri.png) **Client switcher** for CA firms: Kaveri Textiles has its own GSTIN, suppliers, invoices and numbers | ![Kaveri approvals](docs/screenshots/desktop-32-approvals-kaveri.png) **Kaveri approvals**: its own MSME timers, including an overdue one |
| ![How well it works](docs/screenshots/desktop-35-evaluation.png) **How well it works**: the evaluation on the labelled invoices, and which check caught each case | |

On a phone the sidebar becomes a bottom tab bar and the table becomes cards:

<p>
  <img src="docs/screenshots/mobile-01-landing.png" width="170" alt="Mobile landing">
  <img src="docs/screenshots/mobile-02-dashboard.png" width="170" alt="Mobile dashboard">
  <img src="docs/screenshots/mobile-03-invoices.png" width="170" alt="Mobile invoices">
  <img src="docs/screenshots/mobile-04-drawer-gst-fail.png" width="170" alt="Mobile invoice drawer">
  <img src="docs/screenshots/mobile-07-approvals.png" width="170" alt="Mobile approvals">
</p>
<p>
  <img src="docs/screenshots/mobile-14-correction-draft.png" width="170" alt="Mobile corrected-invoice draft">
  <img src="docs/screenshots/mobile-17-drawer-msme.png" width="170" alt="Mobile MSME timer">
  <img src="docs/screenshots/mobile-11-agent-proposal.png" width="170" alt="Mobile AP agent">
  <img src="docs/screenshots/mobile-12-dark-dashboard.png" width="170" alt="Mobile dark mode">
  <img src="docs/screenshots/mobile-31-dashboard-kaveri.png" width="170" alt="Mobile second client business">
  <img src="docs/screenshots/mobile-35-evaluation.png" width="170" alt="Mobile evaluation page">
</p>

## The problem

A small Indian business receives supplier invoices as PDFs and pays them by UPI or bank transfer. Four things go wrong:

1. **Fraud**: fake suppliers, duplicate invoices, "our bank details have changed" emails, invoices with hidden text aimed at AI tools.
2. **GST mistakes**: an invalid or made-up GSTIN, IGST charged where CGST+SGST applies (or the reverse), a GST total that does not add up. These cost the buyer **input tax credit (ITC)** and create notices later.
3. **MSME deadlines**: payments to micro and small suppliers that run past 45 or 15 days make the expense non-deductible for the year (Section 43B(h)). Nobody is watching the clock.
4. **Manual checking** that is slow, so mistakes slip through at month end.

## What it does

Upload an invoice PDF. InvoiceGuard India reads it with Gemini, runs it through GST and fraud checks written as plain code, and then **pays it, holds it for a person, or blocks it**, always with a plain-English reason, a per-invoice GST report and an audit-log entry (timestamps in **IST**).

- **GST-aware extraction**: supplier and buyer GSTIN, place of supply, HSN/SAC per line, GST rate, taxable value, CGST/SGST/IGST and total.
- **GST checks in code** (below), shown per invoice as a pass/fail list and as a step in the invoice's journey.
- **A path for GST failures**: on an on-hold invoice with a GST problem, **Ask supplier for a corrected invoice** drafts an email naming the exact issue (copy it or open it in your mail app; nothing is sent) and logs the request. If you still choose **Approve & pay**, you must give a short reason, which is saved in the audit log. A block-level failure such as a fake GSTIN can never be approved.
- **ITC protected**: the dashboard totals the GST on blocked invoices with an invalid GSTIN or a GST error, with the GST still at risk on held ones shown separately.
- **MSME payment timer**: suppliers marked micro or small get a **Pay by** date and days left, with an alert when 7 days or fewer remain.
- **INR throughout** with Indian number formatting (`₹1,24,000.00`, lakh and crore groupings on the dashboard).
- **Payouts** to the supplier's *saved* UPI ID or bank account, by UPI, IMPS or RTGS depending on the amount. Idempotent, with HOLD-on-failure.
- **AP agent with propose-then-confirm**: ask in plain English; the agent can only recommend, you confirm with a click, and every check is re-run at that moment. The three suggested prompts answer **instantly** (see below).
- **Try it yourself**: a **Download a sample invoice** menu next to Upload gives three realistic PDFs (two valid, one with a GST problem) to upload.
- **For CA firms: several client businesses in one login.** A switcher in the top bar changes between client businesses (the demo has **Bluebird Retail**, Bengaluru, and **Kaveri Textiles**, Coimbatore). Each has its own GSTIN, suppliers, purchase orders, invoices, audit log, ITC, MSME timers, export and agent view; invoices are checked against that business's own GSTIN, and nothing is visible across businesses (this is tested).
- **Tally-friendly export**: **Export for Tally (CSV)** downloads the current business's paid invoices with the columns an accountant needs: Date, Supplier, Supplier GSTIN, Invoice No, Taxable Value, CGST, SGST, IGST, Total, Payment Reference. Dates are DD-MM-YYYY, amounts are plain rupees, the supplier name and GSTIN are the saved, verified ones, and spreadsheet-formula injection is neutralised.
- **How well it works**: an in-app page shows the evaluation on the labelled invoices (cases, fraud and errors caught, valid invoices wrongly held, and **which check caught each one**). It is generated from the real eval run (`python -m eval.run_eval --write`) and a test fails if it ever differs from a fresh run.
- **A fintech-style dashboard**: landing page, sidebar (bottom tab bar on phones), KPI cards, chart, invoice table with search and filters, an **invoice drawer** with a six-step journey (Read, GST checks, Rule checks, AI review, Decision, Payout), light and dark themes, keyboard and screen-reader friendly. Deep links like `/#/invoices/8` open an invoice directly.

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

Fraud checks alongside them (`checks.py`): duplicate invoice, purchase-order match, approved-supplier list, **payee check** (a UPI ID or bank account printed on the invoice that differs from the saved one is blocked), per-payment and daily limits (the daily limit counts the IST day). Then Gemini does a separate review for scam signals and hidden instructions.

The decision (`decide.py`) is a small pure function: any block-level finding or high AI risk blocks; any hold-level finding, medium risk or an AI failure holds; otherwise the invoice is auto-paid. **Only that function or an explicit owner click can lead to a payment.**

### Input tax credit (ITC)
A buyer can claim ITC only on a valid tax invoice from a real, correctly identified supplier with the right tax charged. The **ITC protected** card adds up the GST amount (CGST + SGST + IGST) on blocked or rejected invoices that failed a GST check. Invoices still on hold with a GST failure are shown as "at risk until you decide". Paying an invoice anyway does not remove the risk, which is why approving one asks for a reason.

### MSME payment timer (Section 43B(h))
`backend/app/msme.py`. Under Section 43B(h) of the Income-tax Act, an amount owed to a **micro or small enterprise** is deductible for the year only if it is paid within the time allowed by the MSMED Act: **45 days with a written agreement, otherwise 15 days**, counted from the day of acceptance.

- Each supplier is marked micro, small or neither, with a flag for a written agreement (`seed/data.py`).
- Each invoice stores an IST **accepted date**. Pay by = accepted date + 45 or 15 days. Days left = pay by minus today (IST).
- States: **ok**, **soon** (7 days or fewer left, amber alert) and **overdue** (red alert). Paid invoices no longer show a timer.
- Shown on Approvals, the invoice drawer, the "Needs your attention" list and Suppliers, always with a note that this is guidance, not tax advice.
- Uploaded invoices are accepted today. In the demo, acceptance dates are set relative to the day you load it (Cedar & Pine 5 days left, Pinnacle 2, Orchard 25) so the countdown is meaningful whenever you run it.

### Why it is safe against prompt injection
- The AI never pays anything. It returns schema-validated JSON; plain code decides.
- The payee is always the saved UPI ID or account, never one written on the invoice.
- If the AI review is unavailable or malformed, the invoice is held, never auto-paid.
- Clear signals (hidden instructions to an AI) have a minimum risk floor in code, so a model that under-scores them still gets blocked.

### The AP agent and its instant answers
The agent (`agent.py`) has three tools (list invoices, run checks, propose payment) and **no payment tool**. For speed, the three suggested prompts were **recorded once from a real Gemini run** on the demo data (`seed/agent_cache.json`, rebuilt with `python -m seed.export_agent_cache`). At runtime the recorded tool calls are replayed against the live invoices, so the proposal is always computed fresh by code and only Gemini's wording is reused; the answer is tagged "Instant demo answer". If the invoices have changed from the recorded state, or you ask anything else, it calls Gemini live.

## Payouts

`backend/app/payouts.py` is the payout adapter. The only built-in provider is **`simulated`**, a labelled sandbox with a ledger that behaves like a real rail:

- **Destination** comes from the supplier's saved details. UPI up to Rs 1,00,000; above that (or if the supplier prefers bank) IMPS up to Rs 2,00,000, then RTGS. UPI over the limit with no saved bank account is an error and the invoice is held.
- **Idempotent**: the same payout reference always returns the same payout.
- **Failures**: insufficient sandbox funds (`SANDBOX_BALANCE_PAISE`) and a rejected beneficiary (a saved UPI ID or account containing `fail`) both put the invoice back on hold with the reason.

A real provider (for example RazorpayX Payouts or a bank API) would implement the same two functions and be selected with `PAYOUT_PROVIDER`; the pipeline would not change. That integration is not built or tested here.

## Architecture and scaling

**Today (the prototype).** One FastAPI process and one SQLite file. An upload is processed inside the request: read the PDF with Gemini, run the GST and fraud checks in code, review for scams with Gemini, decide, and (if safe) pay through the simulated payout adapter. It is deliberately simple so the whole decision path can be read and tested end to end (201 tests). Everything that matters for correctness is already in place: integer paise, idempotent payouts, every decision in an audit log, `business_id` on every supplier and invoice, and one pure decision function.

**How it grows.** None of the steps below changes the rules or the pipeline's order; they change where things run and who can see what.

| Concern | Today | In production |
|---|---|---|
| Database | SQLite file, re-seeded on every start on the free host | **PostgreSQL** (managed, backed up, point-in-time recovery). Schema migrations with Alembic instead of the small in-code upgrade. Indexes on `(business_id, status)` and `(supplier_id, invoice_number)`; unique constraints for PO numbers and payout references; `business_id` added to every table (purchase orders, audit log, payouts), not only suppliers and invoices. |
| Invoice processing | Synchronous inside the upload request | **Job queue** (for example Redis with RQ or Celery, or a cloud task queue). Upload stores the PDF in object storage and returns at once; a worker runs read, checks, AI review and decision. Idempotent on the file hash, retries with back-off, and a dead-letter path that ends in HOLD (never auto-pay on a failure, as today). The UI is told by push (SSE or webhook) instead of waiting. |
| Payments | Simulated sandbox adapter | A licensed payout partner behind the same adapter, run by a **separate payout worker** using an outbox table and the existing idempotency reference; webhooks and UTR reconciliation; **maker-checker** (two people) above a limit. The business's money stays with the licensed partner, not with us. |
| Per-business isolation | Every query is scoped by business id in application code, and a test suite proves other businesses' invoices, suppliers, audit rows, exports and agent views are invisible | Real authentication with a user-to-business membership table and roles (owner, accountant, CA). Tokens carry the allowed business ids. PostgreSQL **row-level security** keyed on the current business, so a missing filter in code cannot leak data. Bank details encrypted per business (KMS envelope keys). Object-store prefix and payout wallet per business. |
| Rate limits and cost | 10 MB PDF cap; Gemini failure falls back to HOLD | Per-user and per-business token-bucket limits at the gateway (uploads, agent calls), page-count cap, malware scan on upload, a Gemini circuit breaker and a monthly AI-spend cap per business. |
| Audit log retention | Plain table | **Append-only** (the application role has no UPDATE or DELETE on it), partitioned by month, optionally hash-chained so tampering is detectable. Keep for at least the statutory period for tax records and make it configurable per client (we would default to 8 years and confirm the exact period with the CA); older partitions move to cold storage and can be exported on request. Personal data minimised, and a documented policy for what is sent to the AI model. |
| Operations | Health endpoint, logs without secrets | Structured logs and metrics per business, tracing across API, queue and workers, alerts on queue age, failed payouts and AI errors; containers behind a load balancer with rolling deploys. |

**Why this order of work.** PostgreSQL and the queue first (they remove the two prototype limits: one writer, and processing tied to a web request). Then authentication with row-level security (the point at which a second real firm can safely be added). Then the real payout partner and maker-checker (the point at which money is real).

## Practical rollout

**Who pays.** The natural buyer is the **CA or accounting firm**, because it already serves many small businesses and carries the risk when an invoice is wrong. The small business gets the benefit (fewer errors, protected input tax credit, on-time MSME payments) without a new job. A direct plan for a single business stays available.

**Pricing idea (illustrative, to be validated in a pilot).**

| Plan | Who | Idea |
|---|---|---|
| Business | One small business | A flat monthly fee for up to about 50 invoices, then a small per-invoice charge |
| CA firm | A firm with 10 or more clients | A per-client monthly fee that falls with the number of clients, one login, one switcher, white-label option |
| Pass-through | Everyone | Payout-partner charges passed through at cost |

The value to compare against: the GST and fraud losses avoided (the dashboard's **ITC protected** and **Money saved** cards), the hours of manual checking, and avoided 43B(h) disallowances. The cost side to measure in the pilot is the Gemini cost per invoice (two model calls today, none for cached demo files). No prices have been tested with real customers.

**How a CA firm would onboard clients.**
1. **Set up the firm.** The CA creates the firm account and adds each client business with its GSTIN, checked against the public GST search, with the client's written consent.
2. **Load the master data.** Import suppliers, GSTINs and payment details from the client's Tally or Excel file. Verify each bank account or UPI ID once (a small test transfer) before it can be paid. Flag MSME suppliers and record whether there is a written agreement.
3. **Set the guard rails.** Per-payment and daily limits, who may approve, and which invoices may ever auto-pay.
4. **Shadow mode for 2 to 4 weeks.** Clients forward or upload invoices; InvoiceGuard only checks and recommends, and the CA compares its verdicts with their own review. The result of that comparison is the real accuracy number (the 7/7 and 0/5 here are a small hand-built set).
5. **Go live carefully.** Auto-pay only for valid invoices under the limit from verified suppliers; everything else lands in Approvals; the CA reviews held items for all clients from one switcher.
6. **Month end.** Export paid invoices to Tally (built), review ITC protected and the MSME timers, and keep the audit trail for the client.

**What a real deployment still needs** (not built here): real authentication and roles, a licensed payout partner, live GSTIN verification, e-invoice (IRN) checks, an inbox per business for forwarded invoices, and a data-protection review under India's DPDP Act. The tax outputs (ITC and MSME timer) are guidance, not tax advice.

## Run it

Needs Python 3.12 and Node 20.

```bash
# backend
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env          # GEMINI_API_KEY is optional: the demo data and sample invoices are cached
python -m uvicorn app.main:app --port 8000

# frontend (second terminal): dev server with API proxy, or build once for the backend to serve
cd frontend
npm ci
npm run dev                         # http://localhost:5173
# or: npm run build                 # then open http://localhost:8000
```

Without a `GEMINI_API_KEY`, the 20 demo invoices (both client businesses), the 4 downloadable samples and the agent chips all work, because their Gemini results are cached (real Gemini output). **Uploading your own new PDF, or asking the agent something else, needs a key.**

**Deploy**: `render.yaml` defines a Docker web service named `invoiceguard-india` (separate from the original). The free plan has no persistent disk, so SQLite is re-created and re-seeded on every start.

## Demo steps

See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for the 3-minute flow. In short: click **Try with demo data** (it loads both client businesses); switch client from the top bar; read the cards (including ITC protected); open the failing invoices and read the red GST line; ask a supplier for a corrected invoice; approve one with a reason; watch the MSME timers on Approvals; ask the AP agent to pay the Cedar & Pine invoice and confirm; export paid invoices for Tally; open **How well it works**; or download a sample invoice and upload it yourself.

## Tests and evaluation

```bash
cd backend
python -m pytest                    # 201 tests: GST, checks, payouts, pipeline, timeline, MSME, agent and its cache, samples, IST, multi-business isolation, export, eval page
python -m eval.run_eval             # uses the cached Gemini results; add --live-gemini to call Gemini
```

Result on the 12 labelled invoices (5 valid, 7 fraud or error cases):

| Measure | Result |
|---|---|
| Fraud and error cases caught | **7 / 7** (duplicate, fake GSTIN, wrong tax type, wrong GST total, changed payee, prompt injection, unapproved supplier) |
| Valid invoices wrongly held | **0 / 5** |
| Fraudulent amount stopped | ₹15,14,498.00 of ₹15,14,498.00 |

"Caught" means not auto-paid. Wrong tax type and wrong GST total are **held** for a person (they can be honest mistakes); the rest are **blocked**. This is a small, hand-built test set, so read it as a demonstration that the checks work, not as a measured production accuracy.

A browser-level check of the live site is recorded in [FINAL_REPORT.md](FINAL_REPORT.md).

## Project layout

```
backend/app/   gst.py (GST rules)  checks.py (fraud rules)  decide.py  extract.py  ai_review.py  payouts.py
               pipeline.py  timeline.py  corrections.py  msme.py  agent.py  routes.py  money.py  timeutil.py
               businesses.py (client businesses)  exports.py (Tally CSV)
backend/seed/  data.py (fictional suppliers and invoices)  make_pdfs.py  gemini_cache.json  agent_cache.json
               invoices/ (20 demo PDFs, two businesses)  upload_samples/ (4 downloadable PDFs)
backend/eval/  run_eval.py  results.json (shown in the app)        backend/tests/
frontend/      React + TypeScript dashboard (Vite, lucide icons, Inter font; no UI framework)
docs/          screenshots used in this README
```

Money is stored as integer paise, never floats. Secrets live in `.env` (git-ignored) and are never logged.
