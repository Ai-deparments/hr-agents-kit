import { useEffect, useState } from "react";
import { api, auth, dash } from "../api";
import { Status } from "../ui";

/** Rauf HR Mini App (/m/rauf): candidates with scores + Shortlist / Hired / Reject. HR Telegram IDs only. */
const mini = { mini: true };
const FILTERS: [string, string][] = [["", "All"], ["new", "New"], ["shortlist", "Shortlist"], ["hired", "Hired"], ["rejected", "Rejected"]];
const CRIT: Record<string, string> = { role_fit: "Role fit", specifics: "Specifics", communication: "Communication", motivation: "Motivation" };

export default function RaufMini() {
  const [ready, setReady] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState("shortlist");
  const [data, setData] = useState<any>(null);
  const [open, setOpen] = useState<any | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = (f = filter) => api<any>(`/api/miniapp/rauf/candidates${f ? `?status=${f}` : ""}`, mini).then(setData).catch((e) => setErr(e.message));

  useEffect(() => {
    const w = window.Telegram?.WebApp;
    w?.ready(); w?.expand();
    if (w?.colorScheme) document.documentElement.dataset.theme = w.colorScheme;
    api<{ token: string }>("/api/miniapp/auth", { body: { init_data: w?.initData || "" }, mini: true })
      .then((r) => { auth.mini = r.token; return load(); })
      .then(() => setReady(true))
      .catch((e) => setErr(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { if (!toast) return; const id = setTimeout(() => setToast(null), 2200); return () => clearTimeout(id); }, [toast]);

  const decide = async (id: number, status: string) => {
    try {
      await api(`/api/miniapp/rauf/candidates/${id}/status`, { body: { status }, mini: true });
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("success");
      setToast(status === "hired" ? "Marked as hired" : status === "rejected" ? "Rejected" : "Moved to shortlist");
      setOpen(null); load();
    } catch (x: any) { setErr(x.message); }
  };

  if (err) return <div className="mini"><h1>Rauf · HR</h1><div className="error" style={{ marginTop: 12 }}>{err}</div></div>;
  if (!ready || !data) return <div className="mini muted">Loading…</div>;

  return (
    <div className="mini">
      <h1>Rauf · Nomzodlar</h1>
      <div className="pills" style={{ margin: "10px 0 14px" }}>
        {FILTERS.map(([k, label]) => (
          <button key={k || "all"} className={`pill ${filter === k ? "active" : ""}`} onClick={() => { setFilter(k); load(k); }}>{label}</button>
        ))}
      </div>
      <div className="stack" style={{ gap: 10 }}>
        {data.rows.length === 0 && <div className="muted" style={{ textAlign: "center", padding: 24 }}>No candidates here</div>}
        {data.rows.map((c: any) => (
          <div key={c.id} className="person">
            <div className="top">
              <div style={{ flex: 1 }}><b>{c.full_name}</b><div className="muted small">{dash(c.vacancy)}{c.branch ? ` · ${c.branch}` : ""}</div></div>
              <div style={{ textAlign: "right" }}><b className="num" style={{ fontSize: 20 }}>{dash(c.score)}</b><div><Status s={c.status} /></div></div>
            </div>
            <div className="row small">
              {c.label ? <span className={`badge ${c.label === "strong" ? "b-ok" : c.label === "medium" ? "b-warn" : "b-bad"}`}>{c.label}</span> : <span className="muted">evaluate manually</span>}
              <span className="spacer" /><button className="btn sm ghost" onClick={() => setOpen(open?.id === c.id ? null : c)}>{open?.id === c.id ? "Hide" : "Details"}</button>
            </div>
            {open?.id === c.id && (
              <div className="stack small">
                {Object.keys(CRIT).map((k) => c.breakdown?.[k] && (
                  <div key={k}><div className="row"><b>{CRIT[k]}</b><span className="spacer" /><span className="num">{c.breakdown[k].score}</span></div>
                    <div className="muted">{c.breakdown[k].comment}</div></div>
                ))}
                {c.answers?.map((a: any, i: number) => <div key={i}><b>{a.q}</b><div>{a.a}</div></div>)}
                {c.phone && <a href={`tel:${c.phone}`} className="btn sm">📞 {c.phone}</a>}
              </div>
            )}
            {c.status !== "hired" && c.status !== "rejected" && (
              <div className="seg" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                {c.status !== "shortlist" && <button onClick={() => decide(c.id, "shortlist")}>Shortlist</button>}
                <button className="on-came" onClick={() => decide(c.id, "hired")}>Ishga olindi</button>
                <button className="on-absent" onClick={() => decide(c.id, "rejected")}>Rad etish</button>
              </div>
            )}
          </div>
        ))}
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
