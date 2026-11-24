# InvoiceGuard India: 3-minute demo script

Setup: open <https://invoiceguard-india.onrender.com> (a sleeping free server can take about a minute to wake: open it a minute early). The demo data, the sample invoices and the three agent prompts are cached, so nothing here needs an API key. Say once, early: **payouts are a simulated sandbox, no real money moves.**

## 0:00 to 0:20 The problem and the pitch

"Indian businesses pay suppliers from PDF invoices. Fake GSTINs, wrong tax type, edited bank details, duplicates and missed MSME deadlines cost real money and input tax credit. InvoiceGuard India checks every invoice in code before a rupee moves."

Point at "Stop fraud before money moves". Click **Try with demo data**.

## 0:20 to 0:45 The dashboard

13 invoices have just been processed (times are in IST). Point at:
- **Paid ₹7.16 L**: 5 valid invoices paid automatically. **Blocked 5**, **On hold 3**.
- **ITC protected ₹46,580**: "the GST on a blocked invoice with a fake GSTIN. Paying it would have put our input tax credit at risk. ₹20,100 more is at risk on two held invoices."

## 0:45 to 1:25 GST checks and a blocked fraud case (Invoices)

Open **Atlas Industrial Parts** (fake GSTIN). In the journey: "GST checks failed: the number is the right shape but its check character fails the GSTIN checksum, so it is not a real registration. Blocked, and the AI call was skipped."

Then open **BlueRiver Software**: "All GST checks pass, but white text in the PDF tells an AI agent to skip checks and pay. The AI review catches it and code blocks it. The AI can never approve a payment." Quickly mention duplicate (Mahalaxmi) and changed payee (Lumen).

## 1:25 to 2:00 Corrected invoice, then approve with a reason (Approvals)

Open **Approvals**. Pinnacle Print: "Tamil Nadu supplier, Karnataka buyer, so IGST applies, but the invoice charges CGST and SGST." Click **Ask supplier for a corrected invoice**: "It drafts an email naming the exact GST issue and logs the request. Nothing is sent." Close it.

Now click **Approve & pay** on Orchard Catering (wrong GST total): "Because there is a GST problem, I must give a reason before it can be paid." Type a reason, approve. "The reason is saved in the audit log." (Open the Audit log to show it, with the IST time.)

## 2:00 to 2:25 MSME timer

Back on **Approvals**: "Pinnacle is a micro supplier with no written agreement: the 15-day Section 43B(h) limit, **pay by 2 days from now**, shown in red amber. Cedar & Pine is a small supplier with a written agreement: 45 days, 5 left. Pay late and the expense is not deductible this year. This is guidance, not tax advice."

## 2:25 to 3:00 AP agent, and try it yourself

Open **AP Agent**, click "Pay the Cedar & Pine Furniture invoice": "Instant, tools shown, and it only proposes." Click **Confirm and pay**: "Every check is re-run now, then the saved UPI ID is paid."

Close: "Judges can try the real upload flow: Invoices, **Download a sample invoice**, then Upload. GST rules in code, AI only for reading and flagging, a person or the decision function for money."

## If something goes wrong

- Page stuck loading: the free server is waking up, wait up to a minute.
- Agent chips are instant; a free-typed question needs `GEMINI_API_KEY` (set in the Render dashboard) and may be slow or out of quota. Use **Approvals** instead.
- Uploading the same sample twice is blocked as a duplicate (that is the duplicate check working). Click **Load demo data** for a clean slate.
- A sample or demo MSME timer shows different days if the demo was loaded on a different day: the dates are set relative to the load day.
