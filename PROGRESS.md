# InvoiceGuard India - build progress

Prasunex Innovathon Round 3. Built from the original InvoiceGuard repo. Each step: tests green, `.env` not staged, commit, push.

- [x] 1. Render service renamed to `invoiceguard-india` (separate service from the original)
- [x] 2. GST engine (`backend/app/gst.py`, `money.py`): GSTIN format + mod-36 check character, state codes, place of supply, CGST+SGST vs IGST, GST arithmetic, HSN/SAC, Indian number formatting. 26 new tests.
