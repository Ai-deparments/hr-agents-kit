import { useState } from "react";
import { api, dash } from "../api";
import { Empty, Err, Light, Modal, Status, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

const CRIT: Record<string, string> = { role_fit: "Role fit 40%", specifics: "Specifics 25%", communication: "Communication 15%", motivation: "Motivation 20%" };

export default function Recruiting() {
  const { me } = usePanel();
  const vac = useLoad<any[]>("/api/vacancies");
  const [vid, setVid] = useState<number | null>(null);
  const cands = useLoad<any[]>(`/api/candidates${vid ? `?vacancy_id=${vid}` : ""}`, []);
  const [drafting, setDrafting] = useState(false);
  const [preview, setPreview] = useState<any | null>(null);
  const [cand, setCand] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const write = can(me, "recruiting");
  const setStatus = async (id: number, status: string) => {
    try { await api(`/api/candidates/${id}/status`, { body: { status } }); cands.reload(); setCand(null); } catch (x: any) { setErr(x.message); }
  };
  return (
    <div className="stack" style={{ gap: 14 }}>
      <Err e={err || vac.error || cands.error} />
      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}><h2 style={{ margin: 0 }}>Vacancies</h2><span className="spacer" />
          {!location.pathname.startsWith("/rauf") && <a className="btn" href="/rauf">Rauf panel ↗</a>}
          {write && <button className="btn primary" onClick={() => setDrafting(true)}>+ Draft vacancy</button>}</div>
        <div className="table-wrap"><table>
          <thead><tr><th /><th>Title</th><th>Branch</th><th>Salary</th><th>Schedule</th><th>Status</th><th className="num">SLA</th><th /></tr></thead>
          <tbody>{vac.data?.map((v) => (
            <tr key={v.id} className="click" onClick={() => setVid(vid === v.id ? null : v.id)} style={vid === v.id ? { outline: "2px solid var(--primary)" } : undefined}>
              <td><Light c={v.light} /></td><td><b>{v.title}</b></td><td>{dash(v.branch)}</td><td className="small">{dash(v.salary_text)}</td>
              <td className="small">{dash(v.schedule_text)}</td><td><Status s={v.status} /></td>
              <td className="num">{v.days_open !== null && v.days_open !== undefined ? `${v.days_open}/${v.sla_days}d` : `${v.sla_days}d`}</td>
              <td onClick={(e) => e.stopPropagation()} className="row">
                <button className="btn sm" onClick={() => setPreview(v)}>Ad</button>
                {write && v.status === "draft" && <button className="btn sm primary" onClick={async () => {
                  try { await api(`/api/vacancies/${v.id}/open`, { method: "POST" }); vac.reload(); } catch (x: any) { setErr(x.message); }
                }}>Open</button>}
              </td>
            </tr>
          ))}</tbody>
        </table></div>
        {vac.data?.length === 0 && <Empty />}
      </div>
      <div className="card">
        <h2>Candidates {vid && <span className="muted small">· filtered by vacancy</span>}</h2>
        <div className="note" style={{ marginBottom: 10 }}>No auto-reject: score ≥70 → shortlist, otherwise “new” for HR review. Hire and reject are always set by a person.</div>
        <div className="table-wrap"><table>
          <thead><tr><th>Name</th><th>Vacancy</th><th className="num">Score</th><th>Label</th><th>Status</th><th>Source</th></tr></thead>
          <tbody>{cands.data?.map((c) => (
            <tr key={c.id} className="click" onClick={() => setCand(c)}>
              <td><b>{c.full_name}</b><div className="muted small">{dash(c.phone)}</div></td><td>{dash(c.vacancy)}</td>
              <td className="num"><b>{dash(c.score)}</b></td><td>{c.label ? <span className={`badge ${c.label === "strong" ? "b-ok" : c.label === "medium" ? "b-warn" : "b-bad"}`}>{c.label}</span> : <span className="muted small">evaluate manually</span>}</td>
              <td><Status s={c.status} /></td><td className="small">{c.source}</td>
            </tr>
          ))}</tbody>
        </table></div>
        {cands.data?.length === 0 && <Empty />}
      </div>
      {preview && <Modal title={`Ad · ${preview.title}`} onClose={() => setPreview(null)}>
        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font)", background: "var(--surface-2)", padding: 12, borderRadius: 10, margin: 0 }}>{preview.ad_text}</pre>
      </Modal>}
      {cand && <Modal title={cand.full_name} onClose={() => setCand(null)}>
        <div className="stack">
          <div className="row"><Status s={cand.status} /><b className="num">{dash(cand.score)}</b><span className="muted">{dash(cand.label)}</span></div>
          {Object.keys(CRIT).map((k) => cand.breakdown?.[k] && (
            <div key={k}><div className="row small"><b>{CRIT[k]}</b><span className="spacer" /><span className="num">{cand.breakdown[k].score}</span></div>
              <div className="muted small">{cand.breakdown[k].comment || "no comment — not counted"}</div></div>
          ))}
          {cand.answers?.length > 0 && <div className="stack small">{cand.answers.map((a: any, i: number) => <div key={i}><b>{a.q}</b><div>{a.a}</div></div>)}</div>}
          {write && <div className="row">
            <button className="btn" onClick={() => setStatus(cand.id, "shortlist")}>Shortlist</button>
            <button className="btn primary" onClick={() => setStatus(cand.id, "hired")}>Hired</button>
            <button className="btn danger" onClick={() => setStatus(cand.id, "rejected")}>Reject</button>
          </div>}
        </div>
      </Modal>}
      {drafting && <DraftVacancy onClose={() => setDrafting(false)} onDone={vac.reload} />}
    </div>
  );
}

function DraftVacancy({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { dicts } = usePanel();
  const [f, setF] = useState<any>({ title: "", requirements: "" });
  const [res, setRes] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title="Draft vacancy" onClose={onClose}>
      {res ? (
        <div className="stack">
          {res.missing.length > 0 ? <div className="error">Missing before opening: {res.missing.join(", ")}</div> : <div className="note">Ready — press “Open” in the list to publish.</div>}
          <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font)", background: "var(--surface-2)", padding: 12, borderRadius: 10, margin: 0 }}>{res.preview}</pre>
          <button className="btn primary" onClick={onClose}>Done</button>
        </div>
      ) : (
        <form className="form" onSubmit={async (e) => {
          e.preventDefault();
          try {
            setRes(await api("/api/vacancies", { body: { ...f, branch_id: f.branch_id ? Number(f.branch_id) : null, position_code: f.position_code || null } }));
            onDone();
          } catch (x: any) { setErr(x.message); }
        }}>
          <label className="field">Title<input required value={f.title} onChange={set("title")} /></label>
          <label className="field">Position<select value={f.position_code || ""} onChange={set("position_code")}><option value="">—</option>{dicts.positions.map((p) => <option key={p.code} value={p.code}>{p.title}</option>)}</select></label>
          <label className="field">Branch<select value={f.branch_id || ""} onChange={set("branch_id")}><option value="">—</option>{dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <label className="field">Salary (as HR says it — never invented)<input value={f.salary_text || ""} onChange={set("salary_text")} /></label>
          <label className="field">Schedule<input value={f.schedule_text || ""} onChange={set("schedule_text")} placeholder="24/48, 2/2, 09:00–18:00" /></label>
          <label className="field">Requirements<textarea rows={3} value={f.requirements} onChange={set("requirements")} /></label>
          <Err e={err} />
          <button className="btn primary">Create draft</button>
        </form>
      )}
    </Modal>
  );
}
