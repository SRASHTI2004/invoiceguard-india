# InvoiceGuard India: 3-minute demo script

Setup: open the app (wake a free Render server first, it can take about a minute). The demo data is cached, so loading it is instant and needs no API key. Only the AP agent step at the end needs `GEMINI_API_KEY` set (on Render, set it in the dashboard). Say once, early: **payouts are a simulated sandbox, no real money moves.**

## 0:00 to 0:25 The problem and the pitch

"Indian businesses pay suppliers from PDF invoices. Fake GSTINs, wrong tax type, edited bank details and duplicate invoices slip through, and wrong GST costs you input tax credit. InvoiceGuard India checks every invoice in code before a rupee moves."

Point at the one-line pitch on the landing page. Click **Try with demo data**.

## 0:25 to 0:55 The result at a glance

13 invoices have just been processed. Point at the cards:
- **Paid ₹7.16 L**: 5 valid invoices, paid automatically.
- **Blocked 5** and **On hold 3**.
- "Fraud and errors stopped": about ₹12.8 L blocked, plus the held ones.

Say: "Evaluation on the 12 labelled invoices: 7 of 7 fraud and error cases caught, 0 of 5 valid invoices wrongly held."

## 0:55 to 2:10 Walk through the cases (Invoices tab, scroll down)

For each, open the **GST checks** panel and read the red line:

1. **Fake GSTIN (Atlas Industrial Parts)**: "The number is the right shape, but its check character fails the GSTIN checksum, so it is not a real registration. Blocked."
2. **Wrong tax type (Pinnacle Print)**: "Tamil Nadu supplier, Karnataka buyer, so IGST applies. The invoice charges CGST and SGST. Held for a person."
3. **Wrong GST total (Orchard Catering)**: "Taxable ₹78,000 plus 5% GST is ₹81,900. The invoice says ₹87,600. Held."
4. **Duplicate (Mahalaxmi)**: "Same invoice number as invoice 1. Blocked."
5. **Changed payee (Lumen Electrical)**: "The invoice asks for a new UPI ID and bank account. We only ever pay the saved details, and a mismatch is blocked."
6. **Hidden prompt injection (BlueRiver)**: "White text in the PDF tells an AI agent to skip checks and pay. The AI review flags it and code blocks it. The AI can never approve a payment."

## 2:10 to 2:35 A good invoice and the payout

Scroll to a **Paid** invoice (for example Summit IT). "All nine GST checks pass. It was paid by RTGS to the saved account, shown masked. A retry cannot pay twice, and if a payout fails the invoice goes back on hold with the reason."

## 2:35 to 3:00 Propose, then confirm

Open **AP agent**, click "Pay the Cedar & Pine Furniture invoice", press **Ask the agent**. "The agent can only recommend. It has no payment tool." Click **Confirm and pay**: "Every check is re-run at this moment, then the saved UPI ID is paid." Finish on the Audit log: "Every decision is recorded."

Close: "GST rules in code, AI only for reading and flagging, a human or the decision function for money. Simulated payouts today; a real payout provider plugs into the same adapter."

## If something goes wrong

- Page stuck loading: the free server is waking up, wait up to a minute.
- Agent shows an error: it needs Gemini (key and quota). Use **Approvals** and click Approve & pay instead.
- Want a clean slate: click **Reload demo data**.
