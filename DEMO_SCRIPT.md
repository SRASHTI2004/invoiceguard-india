# InvoiceGuard India: 3-minute demo script

Setup: open <https://invoiceguard-india.onrender.com> (a sleeping free server can take about a minute to wake: open it a minute early). The demo data, the sample invoices and the suggested agent prompts are cached, so nothing here needs an API key. Say once, early: **payouts are a simulated sandbox, no real money moves.**

## 0:00 to 0:20 The problem and the pitch

"Indian businesses pay suppliers from PDF invoices. Fake GSTINs, wrong tax type, edited bank details, duplicates and missed MSME deadlines cost real money and input tax credit. And most small businesses rely on a CA who looks after many of them. InvoiceGuard India checks every invoice in code before a rupee moves."

Point at "Stop fraud before money moves". Click **Try with demo data** (it loads two client businesses).

## 0:20 to 0:40 The dashboard

"Bluebird Retail, 13 invoices, times in IST." Point at **Paid ₹7.16 L**, **Blocked 5**, **On hold 3**, and **ITC protected ₹46,580**: "the GST on a blocked invoice with a fake GSTIN. Paying it would have put our input tax credit at risk."

## 0:40 to 1:05 GST checks and a blocked fraud case (Invoices)

Open **Atlas Industrial Parts**: "The GSTIN is the right shape but fails the checksum, so it is not a real registration. Blocked." Open **BlueRiver Software**: "White text tells an AI agent to skip checks and pay. The AI review flags it, code blocks it. The AI can never approve a payment."

## 1:05 to 1:35 Corrected invoice, then approve with a reason (Approvals)

Pinnacle Print: "Tamil Nadu supplier, Karnataka buyer: IGST should apply, but it charges CGST and SGST." Click **Ask supplier for a corrected invoice**: "A drafted email naming the exact issue, logged, nothing sent." Then **Approve & pay** on Orchard Catering: "With a GST problem I must give a reason first." Type one, approve. "It is in the audit log."

## 1:35 to 1:55 MSME timer

"Pinnacle is a micro supplier with no written agreement: 15-day Section 43B(h) limit, 2 days left. Cedar & Pine has a written agreement: 45 days, 5 left. Guidance, not tax advice."

## 1:55 to 2:25 One login, many clients (the CA story)

Use the switcher in the top bar to open **Kaveri Textiles** (Coimbatore). "Different GSTIN, different suppliers, different invoices, its own ITC and its own overdue MSME alert. Nothing leaks between clients; that is tested." Open Invoices and click **Export for Tally (CSV)**: "Paid invoices with the columns an accountant needs: date, supplier, GSTIN, invoice number, taxable value, CGST, SGST, IGST, total, payment reference."

## 2:25 to 2:45 AP agent

Open **AP Agent**, click "Pay the Chennai Packaging Co. invoice": "Instant, tools shown, and it only proposes." Click **Confirm and pay**: "Every check is re-run now, then the saved UPI ID is paid."

## 2:45 to 3:00 How well it works, and try it yourself

Open **How well it works**: "7 of 7 fraud and error cases caught, 0 of 5 valid invoices wrongly held, with the check that caught each one. It is generated from the real evaluation run, and a test fails if it ever drifts. It is a small hand-built set, so read it as a demonstration, not production accuracy." Close: "You can try the real upload flow yourself: Invoices, **Download a sample invoice**, then Upload."

## If something goes wrong

- Page stuck loading: the free server is waking up, wait up to a minute.
- Agent chips are instant; a free-typed question needs `GEMINI_API_KEY` (set in the Render dashboard) and may be slow or out of quota. Use **Approvals** instead.
- Uploading the same sample twice is blocked as a duplicate (the duplicate check working). Click **Load demo data** for a clean slate (it resets both businesses).
- MSME days differ if the demo was loaded on a different day: acceptance dates are set relative to the day it is loaded.
