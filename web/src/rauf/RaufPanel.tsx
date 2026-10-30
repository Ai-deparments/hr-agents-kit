import { useContext, useEffect, useState } from "react";
import { api, auth, dash, money } from "../api";
import { Lang, LangCtx, tEnum, useT } from "../i18n";
import Login from "../panel/Login";
import Recruiting from "../panel/Recruiting";
import { can, Dicts, Me, PanelCtx } from "../panel/ctx";
import { Empty, Err, Light, Modal, Status, Tile, useLoad } from "../ui";

/** Rauf's own recruiter panel (/rauf): funnel, pipeline, vacancies, archive, ads, integrations. */
const TABS = [
  ["dashboard", "dashboard"], ["pipeline", "rf_pipeline"], ["vacancies", "rf_vacCands"],
  ["archive", "rf_archive"], ["ads", "rf_ads"], ["integrations", "rf_integrations"],
] as const;
type Tab = typeof TABS[number][0];
const STAGES: [string, string][] = [["new", "rf_stNew"], ["shortlist", "rf_stShortlist"], ["hired", "rf_stHired"], ["rejected", "rf_stRejected"]];
const CRIT: Record<string, string> = { role_fit: "crit_role_fit", specifics: "crit_specifics", communication: "crit_communication", motivation: "crit_motivation" };

export default function RaufPanel() {
  const [token, setToken] = useState(auth.panel);
  const [me, setMe] = useState<Me | null>(null);
  const [dicts, setDicts] = useState<Dicts | null>(null);
  const [tab, setTab] = useState<Tab>(() => {
    try { return (localStorage.getItem("hrkit.rauf.tab") as Tab) || "dashboard"; } catch { return "dashboard"; }
  });
  const { lang, setLang } = useContext(LangCtx);
  const t = useT();

  useEffect(() => {
    const out = () => { setToken(null); setMe(null); };
    window.addEventListener("hrkit:logout", out);
    return () => window.removeEventListener("hrkit:logout", out);
  }, []);
  useEffect(() => {
    if (!token) return;
    Promise.all([api<Me>("/api/me"), api<Dicts>("/api/dictionaries")])
      .then(([m, d]) => { setMe(m); setDicts(d); })
      .catch(() => { auth.panel = null; setToken(null); });
  }, [token]);

  if (!token) return <Login onLogin={(tk) => { auth.panel = tk; setToken(tk); }} />;
  if (!me || !dicts) return <div className="login-wrap"><div className="login muted">{t("c_loading")}</div></div>;
  if (!can(me, "recruiting.read")) return <div className="login-wrap"><div className="login">{t("rf_needPerm")} <a href="/">{t("rf_backHr")}</a></div></div>;
  const go = (k: Tab) => { setTab(k); try { localStorage.setItem("hrkit.rauf.tab", k); } catch { /* ignore */ } };
  const reloadDicts = () => api<Dicts>("/api/dictionaries").then(setDicts);

  return (
    <PanelCtx.Provider value={{ me, dicts, reloadDicts, go: () => { location.href = "/"; } }}>
      <div className="app">
        <aside className="side">
          <div className="brand"><span className="logo">{t("rf_brand")}</span></div>
          <nav className="nav">
            {TABS.map(([k, label]) => <button key={k} className="nav-i" aria-current={k === tab ? "page" : undefined} onClick={() => go(k)}>{t(label)}</button>)}
            <a className="nav-i" href="/" style={{ marginTop: 12 }}>← {t("rf_hrPanel")}</a>
          </nav>
        </aside>
        <main className="main">
          <header className="hdr"><div className="hdr-1">
            <h1>{t(TABS.find(([k]) => k === tab)?.[1] || "")}</h1>
            <div className="right">
              <select className="ctl" value={lang} onChange={(e) => setLang(e.target.value as Lang)} aria-label="Language">
                <option value="uz">UZ</option><option value="ru">RU</option><option value="en">EN</option>
              </select>
              <button className="btn btn-o" onClick={() => { auth.panel = null; setToken(null); }}>{t("logout")}</button>
            </div>
            <select className="mobile-nav" value={tab} onChange={(e) => go(e.target.value as Tab)} aria-label="Section">
              {TABS.map(([k, label]) => <option key={k} value={k}>{t(label)}</option>)}
            </select>
          </div></header>
          <div className="page">
          {tab === "dashboard" && <RDashboard />}
          {tab === "pipeline" && <Pipeline write={can(me, "recruiting")} />}
          {tab === "vacancies" && <Recruiting />}
          {tab === "archive" && <Archive />}
          {tab === "ads" && <Ads />}
          {tab === "integrations" && <Integrations />}
          </div>
        </main>
      </div>
    </PanelCtx.Provider>
  );
}

function RDashboard() {
  const t = useT();
  const { data: d, error } = useLoad<any>("/api/rauf/dashboard");
  if (error) return <Err e={error} />;
  if (!d) return <div className="muted">{t("c_loading")}</div>;
  const total = d.candidates || 0;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="grid tiles">
        <Tile label={t("rf_openVac")} value={d.open_vacancies} sub={`${d.draft_vacancies} ${t("rf_drafts")}`} />
        <Tile label={t("rc_candidates")} value={total} sub={`${d.unscored} ${t("rf_toEval")}`} />
        <Tile label={t("rf_stShortlist")} value={d.funnel.shortlist} />
        <Tile label={t("rf_stHired")} value={d.funnel.hired} />
        <Tile label={t("rf_avgScore")} value={dash(d.avg_score)} sub={t("rf_scoreSub")} />
        <Tile label={t("rf_avgDays")} value={dash(d.avg_days_to_close)} />
        <Tile label="SLA" value={<span className="row" style={{ gap: 10 }}><span><Light c="green" /> {d.sla.green}</span><span><Light c="yellow" /> {d.sla.yellow}</span><span><Light c="red" /> {d.sla.red}</span></span>} />
      </div>
      <div className="grid two">
        <div className="card">
          <h2>{t("rf_funnel")}</h2>
          {STAGES.map(([k, label]) => {
            const n = d.funnel[k] || 0;
            return (
              <div key={k} style={{ padding: "6px 0" }}>
                <div className="row small"><b>{t(label)}</b><span className="spacer" /><span className="num">{n}{total >= 10 ? ` · ${Math.round(100 * n / total)}%` : ""}</span></div>
                <div className="bar"><span style={{ width: `${total ? (100 * n) / total : 0}%` }} /></div>
              </div>
            );
          })}
          <div className="muted small" style={{ marginTop: 8 }}>{t("rf_baseNote").replace("{n}", String(total))}</div>
          <h2 style={{ marginTop: 16 }}>{t("rf_bySource")}</h2>
          {Object.keys(d.by_source).length === 0 ? <Empty /> : Object.entries(d.by_source).map(([s, n]) => (
            <div key={s} className="row small" style={{ padding: "3px 0" }}><span>{s}</span><span className="spacer" /><b className="num">{n as number}</b></div>
          ))}
        </div>
        <div className="stack">
          <div className="card">
            <h2>{t("rf_vacSla")}</h2>
            {d.vacancies.length === 0 ? <Empty /> : d.vacancies.map((v: any) => (
              <div key={v.id} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
                <Light c={v.light} /><b>{v.title}</b><span className="muted small">{v.branch}</span><span className="spacer" />
                <span className="num small">{v.days_open}/{v.sla_days} {t("c_dUnit")} · {v.candidates} {t("rf_cand")}</span>
              </div>
            ))}
          </div>
          <div className="card">
            <h2>{t("rf_latest")}</h2>
            {d.recent.length === 0 ? <Empty /> : d.recent.map((c: any) => (
              <div key={c.id} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
                <b>{c.full_name}</b><span className="muted small">{dash(c.vacancy)}</span><span className="spacer" />
                <b className="num">{dash(c.score)}</b><Status s={c.status} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function Pipeline({ write }: { write: boolean }) {
  const t = useT();
  const { data, error, reload } = useLoad<Record<string, any[]>>("/api/rauf/pipeline");
  const [cand, setCand] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const move = async (id: number, status: string) => {
    try { await api(`/api/candidates/${id}/status`, { body: { status } }); setCand(null); reload(); } catch (x: any) { setErr(x.message); }
  };
  if (error) return <Err e={error} />;
  if (!data) return <div className="muted">{t("c_loading")}</div>;
  return (
    <div className="stack" style={{ gap: 12 }}>
      <Err e={err} />
      <div className="note">{t("rf_pipeNote")}</div>
      <div className="kanban">
        {STAGES.map(([k, label]) => (
          <div key={k} className="kcol">
            <div className="row"><b>{t(label)}</b><span className="spacer" /><span className="badge">{data[k]?.length || 0}</span></div>
            {(data[k] || []).map((c) => (
              <button key={c.id} className="kcard" onClick={() => setCand(c)}>
                <div className="row"><b>{c.full_name}</b><span className="spacer" /><b className="num">{dash(c.score)}</b></div>
                <div className="muted small">{dash(c.vacancy)}{c.branch ? ` · ${c.branch}` : ""}</div>
                <div className="small">{c.label ? <span className={`badge ${c.label === "strong" ? "b-ok" : c.label === "medium" ? "b-warn" : "b-bad"}`}>{tEnum(t, "lbl_", c.label)}</span> : <span className="muted">{t("rc_evalManually")}</span>} <span className="muted">· {c.source}</span></div>
              </button>
            ))}
            {(data[k] || []).length === 0 && <div className="muted small" style={{ padding: 8 }}>—</div>}
          </div>
        ))}
      </div>
      {cand && <Modal title={cand.full_name} onClose={() => setCand(null)}>
        <div className="stack">
          <div className="row"><Status s={cand.status} /><b className="num">{dash(cand.score)}</b><span className="muted">{dash(cand.phone)}</span></div>
          {Object.keys(CRIT).map((k) => cand.breakdown?.[k] && (
            <div key={k}><div className="row small"><b>{t(CRIT[k])}</b><span className="spacer" /><span className="num">{cand.breakdown[k].score}</span></div>
              <div className="muted small">{cand.breakdown[k].comment || t("rc_noComment")}</div></div>
          ))}
          {cand.answers?.length > 0 && <div className="stack small">{cand.answers.map((a: any, i: number) => <div key={i}><b>{a.q}</b><div>{a.a}</div></div>)}</div>}
          {write && <div className="row">
            {cand.status !== "shortlist" && <button className="btn" onClick={() => move(cand.id, "shortlist")}>{t("rc_shortlistBtn")}</button>}
            <button className="btn primary" onClick={() => move(cand.id, "hired")}>{t("rc_hiredBtn")}</button>
            <button className="btn danger" onClick={() => move(cand.id, "rejected")}>{t("reject")}</button>
          </div>}
        </div>
      </Modal>}
    </div>
  );
}

function Archive() {
  const t = useT();
  const [q, setQ] = useState("");
  const { data, error } = useLoad<any>(`/api/rauf/archive?q=${encodeURIComponent(q)}`, [q]);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <Err e={error} />
      <input placeholder={t("rf_searchArch")} value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 360 }} />
      <div className="card">
        <h2>{t("rf_candArch")}</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("c_name")}</th><th>{t("c_vacancy")}</th><th className="num">{t("c_score")}</th><th>{t("c_status")}</th><th>{t("c_source")}</th></tr></thead>
          <tbody>{data?.candidates.map((c: any) => (
            <tr key={c.id}><td><b>{c.full_name}</b><div className="muted small">{dash(c.phone)}</div></td><td>{dash(c.vacancy)}</td>
              <td className="num">{dash(c.score)}</td><td><Status s={c.status} /></td><td className="small">{c.source}</td></tr>
          ))}</tbody>
        </table></div>
        {data?.candidates.length === 0 && <Empty />}
      </div>
      <div className="card">
        <h2>{t("rf_closedVac")}</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("c_title")}</th><th>{t("c_branch")}</th><th>{t("rf_opened")}</th><th>{t("rf_closed")}</th><th className="num">{t("c_days")}</th></tr></thead>
          <tbody>{data?.vacancies.map((v: any) => (
            <tr key={v.id}><td><b>{v.title}</b></td><td>{dash(v.branch)}</td><td>{dash(v.opened_at)}</td><td>{dash(v.closed_at)}</td><td className="num">{dash(v.days)}</td></tr>
          ))}</tbody>
        </table></div>
        {data?.vacancies.length === 0 && <Empty />}
      </div>
    </div>
  );
}

function Ads() {
  const t = useT();
  const { data, error } = useLoad<any>("/api/rauf/ads");
  return (
    <div className="card">
      <Err e={error} />
      <div className="note" style={{ marginBottom: 10 }}>{t("rf_adsNote").replace("{sum}", money(data?.confirm_above))}</div>
      <div className="table-wrap"><table>
        <thead><tr><th>{t("rq_channel")}</th><th className="num">{t("rf_subs")}</th><th>{t("c_stageCap")}</th><th className="num">{t("rf_budget")}</th><th className="num">{t("rf_price")}</th><th>{t("rf_postAt")}</th></tr></thead>
        <tbody>{data?.deals.map((d: any) => (
          <tr key={d.id}><td><b>{d.channel}</b></td><td className="num">{money(d.subscribers)}</td><td><span className="badge">{d.stage}</span></td>
            <td className="num">{money(d.budget)}</td><td className="num">{money(d.price)}</td><td>{dash(d.post_at)}</td></tr>
        ))}</tbody>
      </table></div>
      {data?.deals.length === 0 && <Empty text={t("rf_noDeals")} />}
    </div>
  );
}

function Integrations() {
  const t = useT();
  const { data, error } = useLoad<any[]>("/api/rauf/integrations");
  return (
    <div className="card">
      <Err e={error} />
      <div className="note" style={{ marginBottom: 10 }}>{t("rf_intNote")}</div>
      {data?.map((i) => (
        <div key={i.name} className="row" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
          <Light c={i.connected ? "green" : "red"} /><b>{i.name}</b>{i.note && <span className="muted small">{i.note}</span>}
          <span className="spacer" /><span className={`badge ${i.connected ? "b-ok" : ""}`}>{i.connected ? t("rf_connected") : t("rf_notConnected")}</span>
        </div>
      ))}
    </div>
  );
}
