# InvoiceGuard India: final report (Prasunex Innovathon, Round 3)

Live site: <https://invoiceguard-india.onrender.com> · Repo: `main`, tagged **`round3-freeze`** · Live check date: 24 Nov 2026 (IST)

**Status: code freeze.** The last commit before the freeze is the one this report describes; nothing is changed after it.

## 1. What this last pass added

| # | Request | What shipped | Where |
|---|---|---|---|
| 1 | "How well it works" page | In-app page with the evaluation on the 12 labelled invoices: cases, fraud and errors caught (**7 / 7**), valid invoices wrongly held (**0 / 5**), money stopped, and **which check caught each case**. Generated from the real eval run (`python -m eval.run_eval --write` writes `eval/results.json`); a test fails if the file differs from a fresh run, so it cannot drift. Linked from the dashboard and the sidebar. | `eval/run_eval.py`, `Evaluation.tsx` |
| 2 | Multi-business for CA firms | A top-bar switcher between client businesses. Demo data for two: **Bluebird Retail** (Bengaluru, 13 invoices) and **Kaveri Textiles** (Coimbatore, 7 invoices, 5 suppliers, wrong tax type, duplicate, changed payee, a partial delivery with an overdue MSME timer). Each business has its own GSTIN, suppliers, invoices, audit log, ITC, MSME timers, export, samples and agent view. Invoices are checked against that business's own GSTIN. Older databases are upgraded in place. | `businesses.py`, `routes.py`, `Shell.tsx` |
| 3 | Tally-friendly export | **Export for Tally (CSV)**: Date, Supplier, Supplier GSTIN, Invoice No, Taxable Value, CGST, SGST, IGST, Total, Payment Reference. DD-MM-YYYY dates, plain rupee amounts, UTF-8 with BOM, saved supplier name and GSTIN, spreadsheet-formula injection neutralised, one file per business. | `exports.py` |
| 4 | README | New **Architecture and scaling** (PostgreSQL, job queue, per-business isolation with row-level security, rate limits, audit-log retention, real payments) and **Practical rollout** (who pays, illustrative pricing, how a CA firm onboards clients, what is not built). Features, screenshots and counts updated; `DEMO_SCRIPT.md` rewritten around the CA story. | `README.md` |
| 5 | Live check and freeze | Results below. | `docs/live-check/` |

## 2. Automated tests

- Backend: **201 tests pass** (`python -m pytest`), up from 174. New: 18 multi-business isolation tests, 6 export tests, 3 evaluation-page tests (including the staleness guard).
- The isolation tests cover: invoice list, suppliers, summary and ITC, audit log, Tally export, samples and the agent's tools per business; other-business ids returning 404 on read, timeline, approve, reject, correction and refresh; a supplier of another business being unknown; the buyer GSTIN of the right business; daily limits not crossing businesses; agent confirm refusing another business's invoice; per-business agent recordings; and an old database being upgraded.
- Frontend: `npm run build` (TypeScript + Vite) is clean.
- Evaluation (`python -m eval.run_eval`): 7 / 7 and 0 / 5, unchanged by the multi-business work.

## 3. Live site check (real browser)

**Method:** headless Microsoft Edge driven by `puppeteer-core` against the live URL at **1440 x 900** and **390 x 844** (touch, device scale 2). The Chrome extension was not used. The scripts are throwaway harnesses, not part of the repo. They capture console errors, page errors, failed requests and HTTP 5xx.

**Run A (everything from the previous pass, on the new build): 94 of 94 passed.** The live database was empty, so the landing-page flow was exercised too.

| Area | Result |
|---|---|
| Load and landing | Site loads (4.4 s desktop, 2.5 s phone); pitch and big button; no overflow |
| Try with demo data | Dashboard in **1.8 s** (both businesses loaded) |
| Every page | Dashboard, Invoices, Approvals, AP Agent, Suppliers, Audit log: correct heading, no overflow, IST timestamps |
| ITC, MSME, drawer | ITC protected ₹46,580.00; MSME pay-by and days left on all held invoices with the guidance note; six-step journey |
| AP agent chips | All three instant (**0.32 to 0.43 s**), tagged "Instant demo answer", proposals with Confirm, Confirm pays |
| Samples and upload | 3 sample PDFs download; sample 1 and 2 paid, sample 3 held (wrong tax type); drawer opens after upload |
| GST failure path | Corrected-invoice draft names the issue; approve asks for a reason and stays disabled until one is typed; reason and request appear in the audit log |
| Reject, themes | Reject works and ITC updates; dark mode on, persists, light mode back |
| Health | At most two toasts on screen; no console errors, page errors, failed requests or 5xx |

**Run B (this pass's features): 44 of 44 passed**, 22 per viewport.

| Area | Result |
|---|---|
| Switcher | Lists both businesses; starts on Bluebird with its GSTIN; switching to Kaveri changes the GSTIN, KPIs (3 paid, 2 blocked, 2 on hold), attention list, invoices (7), suppliers (its own 5), approvals with MSME timers including "overdue by 3 days", audit log (only invoice ids 14 to 20) |
| Per-business extras | Kaveri sample menu shows its own sample; Kaveri agent chips are its own and answer instantly (**0.40 s**) with a proposal; switching back works; the chosen business is remembered after reload |
| Tally export | Kaveri CSV has the header plus 3 paid rows with correct columns; the button downloads and confirms ("paid-invoices-tally-kaveri-textiles-… with 3 paid invoices") |
| Evaluation page | Opens from the dashboard link; 7 / 7 and 0 / 5; 12 cases with the check that caught each; no overflow |
| Health | No console errors or 5xx at either width |

**Isolation on the live API (direct requests):** business 1 sees 13 invoices and business 2 sees 7; business 1 asking for business 2's invoice returns **404** on read, timeline and approve; business 2 asking for business 1's invoice returns 404; an unknown business returns 404; Tally export returns 5 rows for Bluebird and 3 for Kaveri.

**Issues found during this pass**
1. The switcher truncated the company name (even the short name on phones). **Fixed**: it now fills its space and shows the short name on phones; verified at both widths.
2. The ITC card read "GST on 0 blocked invoices" for a business with none. **Fixed**: it now says there are none yet.
3. My Tally export first used the supplier name as printed on the PDF (for example upper-case). **Fixed**: it exports the saved supplier name and GSTIN.

After the checks I reset the live data (`POST /api/demo/run-samples`), so the site currently shows the clean 20-invoice, two-business demo. A free-plan Render restart re-seeds the database and brings back the landing page.

Screenshots from the live runs are in `docs/live-check/`.

## 4. Limits and honest notes

- **No authentication.** The business is chosen by a header the browser sends, so isolation today is a **data-model and test guarantee, not a security boundary**: anyone who can reach the API can pick any business. The README's architecture section describes the fix (users and roles, tokens carrying allowed businesses, PostgreSQL row-level security). This must be built before a second real firm is onboarded.
- **Two demo businesses**, not three; the code supports any number.
- **Payouts are simulated.** No real money moves. A real payout provider would implement the same adapter; that is not built or tested.
- **The corrected-invoice email is a draft**; the app does not send email.
- **MSME timer and ITC card are guidance, not tax advice.** The clock starts at an "accepted" date stored per invoice (uploads are accepted the day they are uploaded; the demo sets acceptance dates relative to the load day so the countdown is meaningful). ITC protected is GST on blocked or rejected invoices that failed a GST check, with held ones shown as "at risk"; it is an indicator, not a tax computation.
- **Agent instant answers are recordings** of real Gemini runs on the exact demo state of each business; the tools and proposals are recomputed live on every replay. Other questions, or a changed invoice state, go to Gemini live (needs the key and quota).
- **The evaluation set is small and hand-built** (12 invoices for Bluebird; Kaveri's invoices are demo data and not in the evaluation). Read 7 / 7 and 0 / 5 as a demonstration that the checks work, not as production accuracy. The honest accuracy number comes from the shadow-mode pilot described in the README.
- **Not covered by the live run:** uploading an arbitrary new PDF (needs live Gemini; the key is set, but I did not spend quota on a new file), and the keyboard focus-trap checks, which were verified against a local build earlier and have not changed since.
- Pricing and rollout in the README are ideas to validate, not tested with customers.
