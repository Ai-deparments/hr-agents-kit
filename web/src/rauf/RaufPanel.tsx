import { useContext, useEffect, useState } from "react";
import { api, auth, dash, money } from "../api";
import { Lang, LangCtx } from "../i18n";
import Login from "../panel/Login";
import Recruiting from "../panel/Recruiting";
import { can, Dicts, Me, PanelCtx } from "../panel/ctx";
import { Empty, Err, Light, Modal, Status, Tile, useLoad } from "../ui";

/** Rauf's own recruiter panel (/rauf): funnel, pipeline, vacancies, archive, ads, integrations. */
const TABS = [
  ["dashboard", "Dashboard"], ["pipeline", "Pipeline"], ["vacancies", "Vacancies & candidates"],
  ["archive", "Archive"], ["ads", "Channel ads"], ["integrations", "Integrations"],
] as const;
type Tab = typeof TABS[number][0];
const STAGES: [string, string][] = [["new", "New"], ["shortlist", "Shortlist"], ["hired", "Hired"], ["rejected", "Rejected"]];
const CRIT: Record<string, string> = { role_fit: "Role fit 40%", specifics: "Specifics 25%", communication: "Communication 15%", motivation: "Motivation 20%" };

export default function RaufPanel() {
  const [token, setToken] = useState(auth.panel);
  const [me, setMe] = useState<Me | null>(null);
  const [dicts, setDicts] = useState<Dicts | null>(null);
  const [tab, setTab] = useState<Tab>(() => {
    try { return (localStorage.getItem("hrkit.rauf.tab") as Tab) || "dashboard"; } catch { return "dashboard"; }
  });
  const { lang, setLang } = useContext(LangCtx);

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
  if (!me || !dicts) return <div className="login muted">Loading…</div>;
  if (!can(me, "recruiting.read")) return <div className="login"><div className="card">The recruiter panel needs the recruiting permission. <a href="/">Back to HR panel</a></div></div>;
  const go = (k: Tab) => { setTab(k); try { localStorage.setItem("hrkit.rauf.tab", k); } catch { /* ignore */ } };

  return (
    <PanelCtx.Provider value={{ me, dicts }}>
      <div className="shell">
        <aside className="side">
          <div className="brand"><span className="brand-mark">R</span><span>Rauf · Recruiter</span></div>
          <nav className="nav">
            {TABS.map(([k, label]) => <button key={k} className={k === tab ? "active" : ""} onClick={() => go(k)}>{label}</button>)}
            <a className="btn ghost sm" href="/" style={{ marginTop: 12 }}>← HR panel</a>
          </nav>
        </aside>
        <main className="main">
          <div className="topbar">
            <select className="mobile-nav" value={tab} onChange={(e) => go(e.target.value as Tab)} aria-label="Section">
              {TABS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
            <h1>{TABS.find(([k]) => k === tab)?.[1]}</h1>
            <div className="right">
              <span className="badge">{me.full_name || me.username} · {me.role}{me.branch_scope ? ` · ${me.branch_scope.length} br.` : ""}</span>
              <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} aria-label="Language">
                <option value="en">EN</option><option value="uz">UZ</option><option value="ru">RU</option>
              </select>
              <button className="btn sm" onClick={() => { auth.panel = null; setToken(null); }}>Log out</button>
            </div>
          </div>
          {tab === "dashboard" && <RDashboard />}
          {tab === "pipeline" && <Pipeline write={can(me, "recruiting")} />}
          {tab === "vacancies" && <Recruiting />}
          {tab === "archive" && <Archive />}
          {tab === "ads" && <Ads />}
          {tab === "integrations" && <Integrations />}
        </main>
      </div>
    </PanelCtx.Provider>
  );
}

function RDashboard() {
  const { data: d, error } = useLoad<any>("/api/rauf/dashboard");
  if (error) return <Err e={error} />;
  if (!d) return <div className="muted">Loading…</div>;
  const total = d.candidates || 0;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="grid tiles">
        <Tile label="Open vacancies" value={d.open_vacancies} sub={`${d.draft_vacancies} drafts`} />
        <Tile label="Candidates" value={total} sub={`${d.unscored} to evaluate manually`} />
        <Tile label="Shortlist" value={d.funnel.shortlist} />
        <Tile label="Hired" value={d.funnel.hired} />
        <Tile label="Avg score" value={dash(d.avg_score)} sub="0–100, 4 criteria" />
        <Tile label="Avg days to close" value={dash(d.avg_days_to_close)} />
        <Tile label="SLA" value={<span className="row" style={{ gap: 10 }}><span><Light c="green" /> {d.sla.green}</span><span><Light c="yellow" /> {d.sla.yellow}</span><span><Light c="red" /> {d.sla.red}</span></span>} />
      </div>
      <div className="grid two">
        <div className="card">
          <h2>Funnel</h2>
          {STAGES.map(([k, label]) => {
            const n = d.funnel[k] || 0;
            return (
              <div key={k} style={{ padding: "6px 0" }}>
                <div className="row small"><b>{label}</b><span className="spacer" /><span className="num">{n}{total >= 10 ? ` · ${Math.round(100 * n / total)}%` : ""}</span></div>
                <div className="bar"><span style={{ width: `${total ? (100 * n) / total : 0}%` }} /></div>
              </div>
            );
          })}
          <div className="muted small" style={{ marginTop: 8 }}>Base: {total} candidates. Fewer than 10 → counts only, no %.</div>
          <h2 style={{ marginTop: 16 }}>By source</h2>
          {Object.keys(d.by_source).length === 0 ? <Empty /> : Object.entries(d.by_source).map(([s, n]) => (
            <div key={s} className="row small" style={{ padding: "3px 0" }}><span>{s}</span><span className="spacer" /><b className="num">{n as number}</b></div>
          ))}
        </div>
        <div className="stack">
          <div className="card">
            <h2>Vacancies by SLA</h2>
            {d.vacancies.length === 0 ? <Empty /> : d.vacancies.map((v: any) => (
              <div key={v.id} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
                <Light c={v.light} /><b>{v.title}</b><span className="muted small">{v.branch}</span><span className="spacer" />
                <span className="num small">{v.days_open}/{v.sla_days} d · {v.candidates} cand.</span>
              </div>
            ))}
          </div>
          <div className="card">
            <h2>Latest candidates</h2>
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
  const { data, error, reload } = useLoad<Record<string, any[]>>("/api/rauf/pipeline");
  const [cand, setCand] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const move = async (id: number, status: string) => {
    try { await api(`/api/candidates/${id}/status`, { body: { status } }); setCand(null); reload(); } catch (x: any) { setErr(x.message); }
  };
  if (error) return <Err e={error} />;
  if (!data) return <div className="muted">Loading…</div>;
  return (
    <div className="stack" style={{ gap: 12 }}>
      <Err e={err} />
      <div className="note">No auto-reject. Score ≥ 70 moves a candidate to shortlist automatically; “Hired” and “Rejected” are always set by a person.</div>
      <div className="kanban">
        {STAGES.map(([k, label]) => (
          <div key={k} className="kcol">
            <div className="row"><b>{label}</b><span className="spacer" /><span className="badge">{data[k]?.length || 0}</span></div>
            {(data[k] || []).map((c) => (
              <button key={c.id} className="kcard" onClick={() => setCand(c)}>
                <div className="row"><b>{c.full_name}</b><span className="spacer" /><b className="num">{dash(c.score)}</b></div>
                <div className="muted small">{dash(c.vacancy)}{c.branch ? ` · ${c.branch}` : ""}</div>
                <div className="small">{c.label ? <span className={`badge ${c.label === "strong" ? "b-ok" : c.label === "medium" ? "b-warn" : "b-bad"}`}>{c.label}</span> : <span className="muted">evaluate manually</span>} <span className="muted">· {c.source}</span></div>
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
            <div key={k}><div className="row small"><b>{CRIT[k]}</b><span className="spacer" /><span className="num">{cand.breakdown[k].score}</span></div>
              <div className="muted small">{cand.breakdown[k].comment || "no comment — not counted"}</div></div>
          ))}
          {cand.answers?.length > 0 && <div className="stack small">{cand.answers.map((a: any, i: number) => <div key={i}><b>{a.q}</b><div>{a.a}</div></div>)}</div>}
          {write && <div className="row">
            {cand.status !== "shortlist" && <button className="btn" onClick={() => move(cand.id, "shortlist")}>Shortlist</button>}
            <button className="btn primary" onClick={() => move(cand.id, "hired")}>Hired</button>
            <button className="btn danger" onClick={() => move(cand.id, "rejected")}>Reject</button>
          </div>}
        </div>
      </Modal>}
    </div>
  );
}

function Archive() {
  const [q, setQ] = useState("");
  const { data, error } = useLoad<any>(`/api/rauf/archive?q=${encodeURIComponent(q)}`, [q]);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <Err e={error} />
      <input placeholder="Search name, phone, vacancy…" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 360 }} />
      <div className="card">
        <h2>Candidates (hired / rejected)</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>Name</th><th>Vacancy</th><th className="num">Score</th><th>Status</th><th>Source</th></tr></thead>
          <tbody>{data?.candidates.map((c: any) => (
            <tr key={c.id}><td><b>{c.full_name}</b><div className="muted small">{dash(c.phone)}</div></td><td>{dash(c.vacancy)}</td>
              <td className="num">{dash(c.score)}</td><td><Status s={c.status} /></td><td className="small">{c.source}</td></tr>
          ))}</tbody>
        </table></div>
        {data?.candidates.length === 0 && <Empty />}
      </div>
      <div className="card">
        <h2>Closed vacancies</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>Title</th><th>Branch</th><th>Opened</th><th>Closed</th><th className="num">Days</th></tr></thead>
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
  const { data, error } = useLoad<any>("/api/rauf/ads");
  return (
    <div className="card">
      <Err e={error} />
      <div className="note" style={{ marginBottom: 10 }}>The first message to a channel admin is sent only after a person presses “Write”. Money is always paid by a person; sums above {money(data?.confirm_above)} UZS need owner confirmation.</div>
      <div className="table-wrap"><table>
        <thead><tr><th>Channel</th><th className="num">Subscribers</th><th>Stage</th><th className="num">Budget</th><th className="num">Price</th><th>Post at</th></tr></thead>
        <tbody>{data?.deals.map((d: any) => (
          <tr key={d.id}><td><b>{d.channel}</b></td><td className="num">{money(d.subscribers)}</td><td><span className="badge">{d.stage}</span></td>
            <td className="num">{money(d.budget)}</td><td className="num">{money(d.price)}</td><td>{dash(d.post_at)}</td></tr>
        ))}</tbody>
      </table></div>
      {data?.deals.length === 0 && <Empty text="No deals yet — add channels from the ads bot." />}
    </div>
  );
}

function Integrations() {
  const { data, error } = useLoad<any[]>("/api/rauf/integrations");
  return (
    <div className="card">
      <Err e={error} />
      <div className="note" style={{ marginBottom: 10 }}>Only the connection state is shown — key values never leave the server.</div>
      {data?.map((i) => (
        <div key={i.name} className="row" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
          <Light c={i.connected ? "green" : "red"} /><b>{i.name}</b>{i.note && <span className="muted small">{i.note}</span>}
          <span className="spacer" /><span className={`badge ${i.connected ? "b-ok" : ""}`}>{i.connected ? "connected" : "not connected"}</span>
        </div>
      ))}
    </div>
  );
}
