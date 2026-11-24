# InvoiceGuard India: final report (Prasunex Innovathon, Round 3)

Live site: <https://invoiceguard-india.onrender.com> · Repo: `main` · Date of live check: 24 Nov 2026 (IST)

## 1. What was delivered in this final pass

| # | Request | What shipped | Where |
|---|---|---|---|
| 1 | All timestamps in IST | Audit log and journey show e.g. "24 Nov 2026, 5:13 pm IST". The daily payment limit now counts the **IST** day (it previously used the UTC day). | `timeutil.py`, `lib.ts` |
| 2 | Better path for GST failures | **Ask supplier for a corrected invoice** drafts an email naming the exact GST issue(s), shows it (copy or open in mail app), logs `correction_requested`, and keeps the invoice on hold. **Approve & pay** on a GST failure requires a reason (min 8 characters), saved in the audit log. A block-level failure (fake GSTIN) can never be approved. The AP agent can never confirm a GST failure. | `corrections.py`, `pipeline.approve`, `actions.tsx` |
| 3 | Sample invoices to download | **Download a sample invoice** menu next to Upload: 3 realistic PDFs (valid same-state, valid IGST, wrong tax type). They have their own purchase orders, so they behave as described even after the demo data is loaded. | `seed/upload_samples/`, `/api/samples` |
| 4 | ITC protected card | GST amount on blocked or rejected invoices that failed a GST check (₹46,580 in the demo), plus a separate "still at risk on held invoices" line (₹20,100), with a one-line explanation. | `pipeline.itc_summary`, dashboard |
| 5 | MSME payment timer | Suppliers marked micro/small with a written-agreement flag. Pay-by date and days left (45 days with an agreement, 15 without) under Section 43B(h); amber alert at 7 days or fewer, red when overdue; shown on Approvals, the drawer, the attention list and Suppliers, with a "guidance, not tax advice" note. | `msme.py` |
| 6 | Fast AP agent chips | The three suggested prompts were recorded from a real Gemini run and are replayed against the live checks: about 0.4 s, tagged "Instant demo answer", with proposal cards and Confirm. Anything else still goes to Gemini live. | `agent.py`, `seed/agent_cache.json` |
| 7 | Docs | README rewritten (features, screenshots, how GST, ITC and MSME work), `DEMO_SCRIPT.md` (3 minutes, covers all listed items), 23 refreshed screenshots in `docs/screenshots/`. | |
| 8 | Live-site check | Results below. | `docs/live-check/` |

## 2. Automated tests

- Backend: **174 tests pass** (`python -m pytest`), up from 128 at the start of this pass. New coverage: IST conversion and the IST daily limit, approve-with-reason rules, correction drafts, ITC totals, sample download whitelist and each sample's expected result, MSME limits/boundaries/states, agent cache hit/miss/replay/confirm.
- Frontend: `npm run build` (TypeScript + Vite) is clean.
- Evaluation (`python -m eval.run_eval`): **7 / 7** fraud and error cases caught, **0 / 5** valid invoices wrongly held (small hand-built set; read it as a demonstration, not production accuracy).

## 3. Live site check (real browser)

**Method:** headless Microsoft Edge driven by `puppeteer-core` against the live URL, at **1440 x 900** and **390 x 844** (touch, device scale 2). The Chrome extension was not used. The script is a throwaway harness, not part of the repo. It captures console errors, page errors, failed requests and HTTP 5xx on every page.

**Result on the final deployed build: 94 of 94 checks passed** (47 per viewport, including the landing-page checks, which only run when the site is empty).

| Area | What was checked | Result |
|---|---|---|
| Load | Site loads; landing page shows the pitch and the big button; no horizontal overflow | Pass (first load 3.4 s desktop, 1.3 s phone; the server was already awake) |
| Try with demo data | Click it, dashboard appears with KPIs, ITC card (₹46,580.00), chart, 3 attention items | Pass (**1.5 s**) |
| Every page | Dashboard, Invoices, Approvals, AP Agent, Suppliers, Audit log: correct heading, no overflow | Pass |
| IST | Audit log timestamps end in "IST", none say "UTC" | Pass |
| MSME | All 3 held invoices show class, pay-by and days left; alert text and "not tax advice" present | Pass |
| Drawer | Six-step journey in order; GST breakdown and MSME timer present | Pass |
| AP agent | Each of the 3 chips: instant tag, answered in **0.38 to 0.59 s**; chips 1 and 3 show a proposal with Confirm; Confirm pays and lists the result | Pass |
| Samples | Menu lists 3 PDFs; each downloads as a real PDF | Pass |
| Upload | Sample 1 paid, sample 2 paid, sample 3 held with "Wrong tax type"; drawer opens after upload | Pass |
| GST failure path | Corrected-invoice draft names the issue and the supplier's email; approve asks for a reason and stays disabled until one is typed; approving pays; the audit log contains the reason and the correction request | Pass |
| Reject | Reject removes the invoice from Approvals; ITC protected rises accordingly | Pass |
| Themes | Dark mode on, persists after reload, light mode back on | Pass |
| Health | No console errors, page errors, failed requests or 5xx on any page, either viewport | Pass |

Screenshots from the live run are in `docs/live-check/`.

**Issues found by the live run, and what happened to them**
1. *Phone toasts covered the drawer* when several appeared in a row (visible when uploading three samples). **Fixed**: at most two toasts, 5 seconds, text clamped to three lines. Deployed, and the final 94/94 run includes a check for it.
2. *Two false failures in my own test script* (it matched an earlier toast). **Fixed in the script** and rerun clean. The app was not at fault.

After the checks I reset the live data with the demo reset endpoint, so the site is currently showing the 13 clean demo invoices (including the Cedar & Pine invoice). Free-plan Render restarts re-create and re-seed the database, which brings back the landing page.

## 4. Limits and honest notes

- **Payouts are simulated.** No real money moves. A real provider would implement the same adapter; that is not built or tested.
- **The corrected-invoice email is a draft.** The app does not send email; it records that a draft was requested.
- **MSME timer is guidance, not tax advice.** The clock starts at an "accepted" date stored per invoice. Uploaded invoices are accepted on the day of upload. For the demo, acceptance dates are set relative to the day the demo is loaded (Cedar & Pine 5 days left, Pinnacle 2, Orchard 25) so the countdown is meaningful whenever it is shown; this is stated in the README. Real acceptance dates would come from goods-receipt or approval records.
- **ITC protected** is defined as GST on blocked or rejected invoices that failed a GST check; held ones are shown separately as "at risk". It is an indicator, not a tax computation.
- **Agent instant answers are recordings** of a real Gemini run on the exact demo state; the tools and proposals are computed live on every replay, but the wording is reused. If the invoices change or the question is different, Gemini is called live (needs a key and quota).
- **Not covered by the live run:** uploading an arbitrary new PDF (needs live Gemini; the key is set on the site, but I did not spend quota testing a new file there), and keyboard focus-trap behaviour on the live site (verified in a real browser against a local build in the previous pass, and unchanged since).
- The evaluation set is small and hand-built.
