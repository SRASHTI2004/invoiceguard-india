import { Bot, Check, Send, Wrench, X, Zap } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import Markdown from "../Markdown";
import { AgentStep, api, ConfirmResult, inr, Proposal, ProposalItem } from "../api";
import { ErrorState, Spinner, useToast } from "../ui";

const EXAMPLES = ["Pay all held invoices due this week", "What is waiting for approval and why?", "Pay the Cedar & Pine Furniture invoice"];

type Msg =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "agent"; text: string; steps: AgentStep[]; proposal: Proposal | null; cached?: boolean; state: "open" | "dismissed" | "confirmed"; results?: ConfirmResult[] }
  | { id: number; role: "error"; text: string };

function Item({ item }: { item: ProposalItem }) {
  const inv = item.invoice;
  return (
    <div className="prop-item">
      <strong>{inv?.supplier ?? "Invoice"} <span className="muted" style={{ fontWeight: 400 }}>· {inv?.invoice_number} · due {inv?.due_date ?? "?"}</span></strong>
      <span style={{ fontWeight: 700 }}>{inv?.amount}</span>
      {item.reasons.map((r, i) => <span key={i} className="why-n">{r}</span>)}
    </div>
  );
}

export default function AgentPage({ reload }: { reload: () => Promise<void> }) {
  const toast = useToast();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);
  useEffect(() => {
    if (msgs.length === 0) return;
    const el = log.current;
    if (el && el.scrollHeight > el.clientHeight + 2) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" }); // desktop: the log scrolls
    else end.current?.scrollIntoView({ block: "end", behavior: "smooth" }); // phone: the page scrolls
  }, [msgs, busy]);

  const patch = (id: number, p: Partial<Extract<Msg, { role: "agent" }>>) =>
    setMsgs((m) => m.map((x) => (x.id === id && x.role === "agent" ? { ...x, ...p } : x)));

  const send = async (message: string) => {
    const q = message.trim();
    if (!q || busy) return;
    setText("");
    setMsgs((m) => [...m, { id: nextId.current++, role: "user", text: q }]);
    setBusy(true);
    try {
      const res = await api.agent(q);
      const empty = !res.reply && !(res.proposal?.recommended.length || res.proposal?.not_recommended.length);
      setMsgs((m) => [...m, empty
        ? { id: nextId.current++, role: "error", text: "The agent returned no answer. Gemini may be unavailable or out of quota. Try again later or use Approvals." }
        : { id: nextId.current++, role: "agent", text: res.reply, steps: res.steps, proposal: res.proposal, cached: res.cached, state: "open" }]);
    } catch (e) {
      setMsgs((m) => [...m, { id: nextId.current++, role: "error", text: (e as Error).message }]);
    }
    setBusy(false);
  };

  const confirm = async (m: Extract<Msg, { role: "agent" }>) => {
    if (!m.proposal) return;
    setBusy(true);
    try {
      const res = await api.confirmProposal(m.proposal.recommended.map((i) => i.invoice!.id));
      patch(m.id, { state: "confirmed", results: res.results });
      const paid = res.results.filter((r) => r.paid).length;
      toast(`${paid} of ${res.results.length} invoice${res.results.length > 1 ? "s" : ""} paid after a fresh check.`, paid === res.results.length ? "green" : "amber");
    } catch (e) {
      toast((e as Error).message, "red");
    }
    setBusy(false);
    await reload();
  };

  return (
    <>
      <div className="page-head">
        <div><h1>AP Agent</h1><p>The agent can recommend, but only code checks plus your click can move money. It has no payment tool: it proposes, you confirm, and every check is re-run on confirm.</p></div>
      </div>
      <div className="card chat-card">
        <div className="chat-log" ref={log} role="log" aria-live="polite" aria-label="Conversation with the AP agent">
          <div className="msg msg-agent">
            <div className="who"><Bot size={14} aria-hidden="true" />AP Agent</div>
            <div className="bubble">Hi! Ask me about invoices, or ask me to pay some. I will only <strong>propose</strong>; you decide.</div>
          </div>
          {msgs.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="msg msg-user"><div className="bubble">{m.text}</div></div>
            ) : m.role === "error" ? (
              <div key={m.id} className="msg"><ErrorState message={m.text} /></div>
            ) : (
              <div key={m.id} className="msg msg-agent">
                <div className="who"><Bot size={14} aria-hidden="true" />AP Agent{m.cached && <span className="instant" title="A recorded answer from a real Gemini run on the demo data. The checks and the proposal below were computed live just now."><Zap size={12} aria-hidden="true" />Instant demo answer</span>}</div>
                {m.steps.length > 0 && (
                  <div className="tools" aria-label="Tools the agent used">
                    {m.steps.map((s, i) => (
                      <span key={i} className="tool"><Wrench size={12} aria-hidden="true" /><code>{s.tool}</code>{Object.keys(s.args).length > 0 && <span>{Object.entries(s.args).map(([k, v]) => `${k}=${v}`).join(", ")}</span>}</span>
                    ))}
                  </div>
                )}
                {m.text && <div className="bubble md"><Markdown text={m.text} /></div>}
                {m.proposal && (m.proposal.recommended.length > 0 || m.proposal.not_recommended.length > 0) && m.state !== "dismissed" && (
                  <div className="proposal">
                    <h4>Proposal {m.state === "confirmed" ? "(confirmed)" : "(nothing has been paid yet)"}</h4>
                    {m.proposal.recommended.length > 0 ? m.proposal.recommended.map((it) => <Item key={it.invoice!.id} item={it} />) : <p className="muted">The agent does not recommend paying anything.</p>}
                    {m.proposal.not_recommended.length > 0 && <><h4>Not recommended</h4>{m.proposal.not_recommended.map((it, i) => <Item key={i} item={it} />)}</>}
                    {m.state === "open" && m.proposal.recommended.length > 0 && (
                      <div className="row-actions">
                        <button className="btn btn-primary" disabled={busy} onClick={() => confirm(m)}>
                          <Check size={16} aria-hidden="true" />Confirm and pay {m.proposal.recommended.length} · {inr(m.proposal.total_recommended_paise)}
                        </button>
                        <button className="btn" disabled={busy} onClick={() => patch(m.id, { state: "dismissed" })}><X size={16} aria-hidden="true" />Dismiss</button>
                      </div>
                    )}
                    {m.results && (
                      <ul style={{ margin: 0, paddingLeft: 20 }}>
                        {m.results.map((r) => <li key={r.invoice_id}>Invoice #{r.invoice_id}: <strong>{r.paid ? "paid" : "not paid"}</strong>. {r.message}</li>)}
                      </ul>
                    )}
                  </div>
                )}
                {m.state === "dismissed" && <div className="muted" style={{ fontSize: "0.85rem" }}>Proposal dismissed. Nothing was paid.</div>}
              </div>
            )
          )}
          {busy && <div className="msg msg-agent"><div className="bubble"><Spinner label="The agent is checking your invoices…" /></div></div>}
          <div ref={end} />
        </div>
        <div className="composer">
          {msgs.length === 0 && (
            <div className="chips" role="group" aria-label="Example requests">
              {EXAMPLES.map((ex) => <button key={ex} className="chip" onClick={() => send(ex)} disabled={busy}>{ex}</button>)}
            </div>
          )}
          <form onSubmit={(e: FormEvent) => { e.preventDefault(); send(text); }}>
            <input value={text} onChange={(e) => setText(e.target.value)} maxLength={500} placeholder="Ask the agent, for example: pay all held invoices due this week" aria-label="Message to the AP agent" disabled={busy} />
            <button className="btn btn-brand" type="submit" disabled={busy || !text.trim()}><Send size={16} aria-hidden="true" />Send</button>
          </form>
        </div>
      </div>
    </>
  );
}
