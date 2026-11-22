import {
  AlertCircle, CheckCircle2, CircleDashed, Clock, Info, Loader2, MinusCircle, PauseCircle, ShieldX, X, XCircle,
  type LucideIcon,
} from "lucide-react";
import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Invoice } from "./api";
import { failedChecks } from "./lib";

/* ---- status badges: always icon + text + colour, never colour alone ---------------------------------------------- */
type Tone = "green" | "amber" | "red" | "grey";
const STATUS: Record<string, { label: string; tone: Tone; Icon: LucideIcon }> = {
  PAID: { label: "Paid", tone: "green", Icon: CheckCircle2 },
  AUTO_PAY: { label: "Auto-pay", tone: "green", Icon: CheckCircle2 },
  SUCCESS: { label: "Settled", tone: "green", Icon: CheckCircle2 },
  HELD: { label: "On hold", tone: "amber", Icon: PauseCircle },
  HOLD: { label: "On hold", tone: "amber", Icon: PauseCircle },
  BLOCKED: { label: "Blocked", tone: "red", Icon: ShieldX },
  BLOCK: { label: "Blocked", tone: "red", Icon: ShieldX },
  REJECTED: { label: "Rejected", tone: "red", Icon: XCircle },
  FAILED: { label: "Failed", tone: "red", Icon: XCircle },
  PENDING: { label: "Pending", tone: "grey", Icon: Clock },
  PAYING: { label: "Pending", tone: "grey", Icon: Clock },
  RECEIVED: { label: "Pending", tone: "grey", Icon: Clock },
};

export function StatusBadge({ status, size = "md" }: { status: string | null; size?: "sm" | "md" }) {
  if (!status) return null;
  const m = STATUS[status] ?? { label: status, tone: "grey" as Tone, Icon: CircleDashed };
  return (
    <span className={`badge tone-${m.tone} badge-${size}`}>
      <m.Icon size={size === "sm" ? 12 : 14} aria-hidden="true" />
      {m.label}
    </span>
  );
}

export function GstBadge({ inv }: { inv: Invoice }) {
  const total = inv.gst_report?.length ?? 0;
  if (total === 0) return <span className="badge tone-grey badge-sm"><MinusCircle size={12} aria-hidden="true" />GST not run</span>;
  const bad = failedChecks(inv);
  return bad === 0 ? (
    <span className="badge tone-green badge-sm"><CheckCircle2 size={12} aria-hidden="true" />GST {total}/{total}</span>
  ) : (
    <span className="badge tone-red badge-sm"><XCircle size={12} aria-hidden="true" />{bad} GST {bad === 1 ? "fail" : "fails"}</span>
  );
}

export const StepIcon: Record<string, { Icon: LucideIcon; label: string }> = {
  pass: { Icon: CheckCircle2, label: "Passed" },
  warn: { Icon: AlertCircle, label: "Needs a person" },
  fail: { Icon: XCircle, label: "Failed" },
  skipped: { Icon: MinusCircle, label: "Skipped" },
  pending: { Icon: Clock, label: "Pending" },
};

/* ---- state blocks ------------------------------------------------------------------------------------------------ */
export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spin-wrap" role="status">
      <Loader2 className="spin" size={16} aria-hidden="true" />
      {label}
    </span>
  );
}

export function Skeleton({ h = 16, w = "100%", r = 8 }: { h?: number; w?: number | string; r?: number }) {
  return <span className="skeleton" style={{ height: h, width: w, borderRadius: r }} aria-hidden="true" />;
}

export function SkeletonCards({ n = 4 }: { n?: number }) {
  return (
    <div className="kpis" role="status" aria-label="Loading">
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="card kpi"><Skeleton h={12} w="40%" /><Skeleton h={30} w="70%" r={10} /><Skeleton h={12} w="55%" /></div>
      ))}
    </div>
  );
}

export function EmptyState({ icon: Icon = Info, title, text, action }: { icon?: LucideIcon; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty-icon"><Icon size={26} aria-hidden="true" /></span>
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="alert tone-red" role="alert">
      <XCircle size={18} aria-hidden="true" />
      <div><strong>Something went wrong</strong><div>{message}</div></div>
      {onRetry && <button className="btn btn-sm" onClick={onRetry}>Try again</button>}
    </div>
  );
}

/* ---- toasts (aria-live) ------------------------------------------------------------------------------------------ */
interface Toast { id: number; text: string; tone: Tone }
const ToastCtx = createContext<(text: string, tone?: Tone) => void>(() => undefined);
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Tone = "green") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, text, tone }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite" aria-atomic="false">
        {toasts.map((t) => (
          <div key={t.id} className={`toast tone-${t.tone}`}>
            {t.tone === "red" ? <XCircle size={16} aria-hidden="true" /> : t.tone === "amber" ? <AlertCircle size={16} aria-hidden="true" /> : <CheckCircle2 size={16} aria-hidden="true" />}
            <span>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/* ---- overlay: accessible modal (drawer or centred dialog) with focus trap, Escape, focus restore ------------------ */
const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

const overlayStack: HTMLElement[] = []; // only the topmost overlay reacts to Escape / Tab

export function Overlay({ label, onClose, variant, children }: { label: string; onClose: () => void; variant: "drawer" | "center"; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const node = ref.current!;
    (node.querySelector<HTMLElement>("[data-autofocus]") ?? node).focus();
    document.body.style.overflow = "hidden";
    overlayStack.push(node);
    const onKey = (e: KeyboardEvent) => {
      if (overlayStack[overlayStack.length - 1] !== node) return;
      if (e.key === "Escape") { e.stopPropagation(); onClose(); }
      if (e.key !== "Tab") return;
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => el.offsetParent !== null);
      if (items.length === 0) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      overlayStack.splice(overlayStack.indexOf(node), 1);
      if (overlayStack.length === 0) document.body.style.overflow = "";
      previous?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className={`overlay overlay-${variant}`}>
      <div className="scrim" onClick={onClose} aria-hidden="true" />
      <div ref={ref} className="sheet" role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}>
        {children}
      </div>
    </div>
  );
}

export function CloseButton({ onClose }: { onClose: () => void }) {
  return (
    <button className="icon-btn" onClick={onClose} aria-label="Close">
      <X size={18} aria-hidden="true" />
    </button>
  );
}

export function ConfirmDialog({ title, body, confirmLabel, tone = "primary", onConfirm, onCancel }: {
  title: string; body: ReactNode; confirmLabel: string; tone?: "primary" | "danger"; onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <Overlay label={title} onClose={onCancel} variant="center">
      <h2 className="dialog-title">{title}</h2>
      <div className="dialog-body">{body}</div>
      <div className="dialog-actions">
        <button className="btn" onClick={onCancel}>Cancel</button>
        <button className={tone === "danger" ? "btn btn-danger" : "btn btn-primary"} data-autofocus onClick={onConfirm}>{confirmLabel}</button>
      </div>
    </Overlay>
  );
}
