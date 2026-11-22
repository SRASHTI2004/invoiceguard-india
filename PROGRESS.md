# InvoiceGuard India - build progress

Prasunex Innovathon Round 3. Built from the original InvoiceGuard repo. Each step: tests green, `.env` not staged, commit, push.

- [x] 1. Render service renamed to `invoiceguard-india` (separate service from the original)
- [x] 2. GST engine (`backend/app/gst.py`, `money.py`): GSTIN format + mod-36 check character, state codes, place of supply, CGST+SGST vs IGST, GST arithmetic, HSN/SAC, Indian number formatting. 26 new tests.
- [x] 3. Payout adapter (`payouts.py`): saved UPI ID / bank account only, rail by amount (UPI up to Rs 1 lakh, IMPS, RTGS), idempotent on `ref`, labelled SIMULATED SANDBOX, HOLD-on-failure (insufficient funds, rejected beneficiary). PayPal removed. 13 tests.
- [x] 4. India data layer: GST-aware extraction, checks wired into the firewall (`checks.py`), per-invoice GST report stored, 12 fictional suppliers with valid GSTINs, 13 GST sample PDFs, real Gemini results cached (`seed/gemini_cache.json`, 26 entries), eval reports 7/7 fraud caught and 0/5 valid wrongly held. 128 tests green.
- [x] 5. UI rebuilt (AG Grid removed): landing hero with big "Try with demo data", summary cards (Rs, lakh/crore), status badges, invoice cards with per-invoice GST check report + tax breakdown, supplier cards, audit feed, mobile layout, light/dark. Build is clean.
