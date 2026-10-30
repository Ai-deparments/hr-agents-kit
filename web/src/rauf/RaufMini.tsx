import { useEffect, useState } from "react";
import { api, auth, dash } from "../api";
import { tEnum, useT } from "../i18n";
import { Status } from "../ui";

/** Rauf HR Mini App (/m/rauf): candidates with scores + Shortlist / Hired / Reject. HR Telegram IDs only. */
const mini = { mini: true };
const FILTERS: [string, string][] = [["", "all"], ["new", "rf_stNew"], ["shortlist", "rf_stShortlist"], ["hired", "rf_stHired"], ["rejected", "rf_stRejected"]];
const CRIT: Record<string, string> = { role_fit: "crit2_role_fit", specifics: "crit2_specifics", communication: "crit2_communication", motivation: "crit2_motivation" };

export default function RaufMini() {
  const t = useT();
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
      setToast(status === "hired" ? t("rm_hiredToast") : status === "rejected" ? t("rm_rejectedToast") : t("rm_movedToast"));
      setOpen(null); load();
    } catch (x: any) { setErr(x.message); }
  };

  if (err) return <div className="mini"><h1>Rauf · HR</h1><div className="error" style={{ marginTop: 12 }}>{err}</div></div>;
  if (!ready || !data) return <div className="mini muted">{t("c_loading")}</div>;

  return (
    <div className="mini">
      <h1>Rauf · {t("rc_candidates")}</h1>
      <div className="pills" style={{ margin: "10px 0 14px" }}>
        {FILTERS.map(([k, label]) => (
          <button key={k || "all"} className={`pill ${filter === k ? "active" : ""}`} onClick={() => { setFilter(k); load(k); }}>{t(label)}</button>
        ))}
      </div>
      <div className="stack" style={{ gap: 10 }}>
        {data.rows.length === 0 && <div className="muted" style={{ textAlign: "center", padding: 24 }}>{t("rm_none")}</div>}
        {data.rows.map((c: any) => (
          <div key={c.id} className="person">
            <div className="top">
              <div style={{ flex: 1 }}><b>{c.full_name}</b><div className="muted small">{dash(c.vacancy)}{c.branch ? ` · ${c.branch}` : ""}</div></div>
              <div style={{ textAlign: "right" }}><b className="num" style={{ fontSize: 20 }}>{dash(c.score)}</b><div><Status s={c.status} /></div></div>
            </div>
            <div className="row small">
              {c.label ? <span className={`badge ${c.label === "strong" ? "b-ok" : c.label === "medium" ? "b-warn" : "b-bad"}`}>{tEnum(t, "lbl_", c.label)}</span> : <span className="muted">{t("rc_evalManually")}</span>}
              <span className="spacer" /><button className="btn sm ghost" onClick={() => setOpen(open?.id === c.id ? null : c)}>{open?.id === c.id ? t("rm_hide") : t("rm_details")}</button>
            </div>
            {open?.id === c.id && (
              <div className="stack small">
                {Object.keys(CRIT).map((k) => c.breakdown?.[k] && (
                  <div key={k}><div className="row"><b>{t(CRIT[k])}</b><span className="spacer" /><span className="num">{c.breakdown[k].score}</span></div>
                    <div className="muted">{c.breakdown[k].comment}</div></div>
                ))}
                {c.answers?.map((a: any, i: number) => <div key={i}><b>{a.q}</b><div>{a.a}</div></div>)}
                {c.phone && <a href={`tel:${c.phone}`} className="btn sm">📞 {c.phone}</a>}
              </div>
            )}
            {c.status !== "hired" && c.status !== "rejected" && (
              <div className="seg" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                {c.status !== "shortlist" && <button onClick={() => decide(c.id, "shortlist")}>{t("rc_shortlistBtn")}</button>}
                <button className="on-came" onClick={() => decide(c.id, "hired")}>{t("rc_hiredBtn")}</button>
                <button className="on-absent" onClick={() => decide(c.id, "rejected")}>{t("reject")}</button>
              </div>
            )}
          </div>
        ))}
      </div>
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
