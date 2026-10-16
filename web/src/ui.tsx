import { ReactNode, useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { useT } from "./i18n";

export function useLoad<T>(path: string | null, deps: unknown[] = [], mini = false) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const reload = useCallback(() => {
    if (!path) return;
    setLoading(true);
    api<T>(path, { mini })
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(() => { reload(); }, [reload]);
  return { data, error, loading, reload, setData };
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-label={title}>
        <div className="row" style={{ marginBottom: 14 }}>
          <h2 style={{ margin: 0 }}>{title}</h2>
          <span className="spacer" />
          <button className="btn ghost sm" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Drawer({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <aside className="drawer">
        <div className="row"><span className="spacer" /><button className="btn ghost sm" onClick={onClose}>✕</button></div>
        {children}
      </aside>
    </>
  );
}

/** Every human decision in this system needs a reason. */
export function ReasonModal({ title, confirmLabel, onSubmit, onClose, extra }: {
  title: string; confirmLabel?: string; onClose: () => void;
  onSubmit: (reason: string) => Promise<unknown>; extra?: ReactNode;
}) {
  const t = useT();
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={title} onClose={onClose}>
      <form className="stack" onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try { await onSubmit(reason); onClose(); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
      }}>
        {extra}
        <label className="field">{t("reason")}
          <textarea rows={3} required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        {err && <div className="error">{err}</div>}
        <div className="row"><span className="spacer" />
          <button type="button" className="btn" onClick={onClose}>{t("cancel")}</button>
          <button className="btn primary" disabled={busy || reason.trim().length < 3}>{confirmLabel || t("save")}</button>
        </div>
      </form>
    </Modal>
  );
}

const STATUS: Record<string, [string, string]> = {
  present: ["came", "b-ok"], late: ["late", "b-warn"], on_shift: ["on shift", "b-info"], absent: ["absent", "b-bad"],
  leave: ["leave", "b-info"], unmarked: ["not marked", ""], off: ["day off", ""], needs_review: ["review", "b-warn"],
  conflict: ["conflict", "b-bad"], not_employed: ["—", ""],
  pending: ["pending", "b-warn"], approved: ["approved", "b-ok"], rejected: ["rejected", "b-bad"],
  new: ["new", "b-info"], shortlist: ["shortlist", "b-ok"], hired: ["hired", "b-ok"],
  draft: ["draft", ""], open: ["open", "b-ok"], closed: ["closed", ""], calculated: ["calculated", "b-info"], paid: ["paid", "b-ok"],
  probation: ["probation", "b-warn"], active: ["active", "b-ok"], fired: ["fired", "b-bad"],
};

export function Status({ s }: { s: string | null | undefined }) {
  if (!s) return <span className="badge">—</span>;
  const [label, cls] = STATUS[s] || [s, ""];
  return <span className={`badge ${cls}`}>{label}</span>;
}

export function Light({ c }: { c?: string | null }) {
  return <span className={`dot ${c || ""}`} title={c || ""} />;
}

export function Err({ e }: { e: string | null }) {
  return e ? <div className="error">{e}</div> : null;
}

export function Tile({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="card tile">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export function Empty({ text = "Nothing here yet" }: { text?: string }) {
  return <div className="muted" style={{ padding: "18px 0", textAlign: "center" }}>{text}</div>;
}
