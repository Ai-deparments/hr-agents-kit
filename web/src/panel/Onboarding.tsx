import { useState } from "react";
import { api, dash } from "../api";
import { Empty, Err, Light, Modal, Tile, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

export function Onboarding() {
  const { me } = usePanel();
  const { data: s, error, reload } = useLoad<any>("/api/onboarding");
  const [open, setOpen] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [score, setScore] = useState<Record<number, string>>({});
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="stack" style={{ gap: 14 }}>
      {s && <div className="grid tiles">
        <Tile label="On onboarding" value={s.total} /><Tile label="Behind (red)" value={s.behind} />
        <Tile label="Without mentor" value={s.no_mentor} /><Tile label="No test after day 25" value={s.no_test} />
      </div>}
      <div className="note">Facts only: whether probation is passed is decided by the manager. Score ≥80 good, ≥60 satisfactory, lower — tell the manager.</div>
      <Err e={error || err} />
      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}><h2 style={{ margin: 0 }}>Plans</h2><span className="spacer" />
          {can(me, "onboarding") && <button className="btn primary" onClick={() => setAdding(true)}>+ Add to onboarding</button>}</div>
        {s?.plans.length === 0 && <Empty />}
        <div className="stack">
          {s?.plans.map((p: any) => (
            <div key={p.plan_id} className="person">
              <div className="top" style={{ cursor: "pointer" }} onClick={() => setOpen(open === p.plan_id ? null : p.plan_id)}>
                <Light c={p.light} />
                <div style={{ flex: 1 }}><b>{p.full_name}</b><div className="muted small">{dash(p.position)} · {dash(p.branch)} · mentor {dash(p.mentor)}</div></div>
                <div className="num small" style={{ textAlign: "right" }}>day {p.day} · stage {p.stage}<div><b>{p.progress_pct}%</b> ({p.done}/{p.due})</div></div>
              </div>
              <div className="row small">{Object.entries(p.scores).map(([st, v]: any) => <span key={st} className={`badge ${v.score >= 80 ? "b-ok" : v.score >= 60 ? "b-warn" : "b-bad"}`}>{st}d: {v.score} {v.label}</span>)}</div>
              {open === p.plan_id && (
                <div className="stack">
                  {p.items.map((i: any) => (
                    <label key={i.id} className="row small" style={{ cursor: "pointer" }}>
                      <input type="checkbox" checked={i.done} onChange={async (e) => {
                        try { await api(`/api/onboarding/items/${i.id}?done=${e.target.checked}`, { method: "POST" }); reload(); } catch (x: any) { setErr(x.message); }
                      }} /> <span className="badge">{i.stage}</span> {i.title}
                    </label>
                  ))}
                  <div className="row">
                    <input type="number" min={0} max={100} placeholder="Test score 0–100" value={score[p.plan_id] || ""} onChange={(e) => setScore({ ...score, [p.plan_id]: e.target.value })} style={{ width: 160 }} />
                    <button className="btn" disabled={!score[p.plan_id]} onClick={async () => {
                      try { await api(`/api/onboarding/${p.plan_id}/score`, { body: { score: Number(score[p.plan_id]) } }); setScore({ ...score, [p.plan_id]: "" }); reload(); }
                      catch (x: any) { setErr(x.message); }
                    }}>Save score (stage {p.stage})</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      {adding && <AddPlan onClose={() => setAdding(false)} onDone={reload} />}
    </div>
  );
}

function AddPlan({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const emps = useLoad<any[]>("/api/employees");
  const [f, setF] = useState<any>({});
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal title="Add to onboarding" onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try { await api("/api/onboarding", { body: { employee_id: Number(f.employee_id), mentor: f.mentor || null, start_date: f.start_date || null } }); onDone(); onClose(); }
        catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">Employee<select required value={f.employee_id || ""} onChange={(e) => setF({ ...f, employee_id: e.target.value })}>
          <option value="">Choose…</option>{emps.data?.filter((e) => e.status !== "fired").map((e) => <option key={e.id} value={e.id}>{e.full_name} — {dash(e.position)}</option>)}</select></label>
        <label className="field">Mentor<input value={f.mentor || ""} onChange={(e) => setF({ ...f, mentor: e.target.value })} /></label>
        <label className="field">Start date (default: hire date)<input type="date" value={f.start_date || ""} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></label>
        <p className="muted small" style={{ margin: 0 }}>The checklist is created from the position template in company.yaml.</p>
        <Err e={err} />
        <button className="btn primary">Create plan</button>
      </form>
    </Modal>
  );
}

export function Documents() {
  const { me } = usePanel();
  const [days, setDays] = useState(60);
  const { data, error, reload } = useLoad<any[]>(`/api/documents/expiring?days=${days}`, []);
  const [adding, setAdding] = useState(false);
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="muted">Expiring within</span>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>{[30, 60, 90, 180].map((d) => <option key={d} value={d}>{d} days</option>)}</select>
        <span className="spacer" />{can(me, "hr.write") && <button className="btn primary" onClick={() => setAdding(true)}>+ Document</button>}
      </div>
      <Err e={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>Employee</th><th>Branch</th><th>Document</th><th>Expires</th><th className="num">Days left</th></tr></thead>
        <tbody>{data?.map((d) => (
          <tr key={d.id}><td><b>{d.full_name}</b></td><td>{d.branch}</td><td>{d.title}</td><td className="mono">{d.expires}</td>
            <td className="num"><span className={`badge ${d.expired ? "b-bad" : d.days_left <= 30 ? "b-warn" : ""}`}>{d.expired ? "expired" : d.days_left}</span></td></tr>
        ))}</tbody>
      </table></div>
      {data?.length === 0 && <Empty text="Nothing expires in this period" />}
      {adding && <AddDoc onClose={() => setAdding(false)} onDone={reload} />}
    </div>
  );
}

function AddDoc({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const emps = useLoad<any[]>("/api/employees");
  const cfg = useLoad<any>("/api/config/public");
  const [f, setF] = useState<any>({});
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title="Add document" onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try { await api("/api/documents", { body: { ...f, employee_id: Number(f.employee_id), issued: f.issued || null, expires: f.expires || null } }); onDone(); onClose(); }
        catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">Employee<select required value={f.employee_id || ""} onChange={set("employee_id")}><option value="">Choose…</option>
          {emps.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}</select></label>
        <label className="field">Type<select required value={f.doc_type || ""} onChange={set("doc_type")}><option value="">Choose…</option>
          {cfg.data?.documents?.map((d: any) => <option key={d.code} value={d.code}>{d.title}</option>)}</select></label>
        <label className="field">Number<input value={f.number || ""} onChange={set("number")} /></label>
        <label className="field">Issued<input type="date" value={f.issued || ""} onChange={set("issued")} /></label>
        <label className="field">Expires<input type="date" value={f.expires || ""} onChange={set("expires")} /></label>
        <Err e={err} />
        <button className="btn primary">Save</button>
      </form>
    </Modal>
  );
}
