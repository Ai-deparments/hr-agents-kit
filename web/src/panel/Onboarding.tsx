import { useState } from "react";
import { api, dash } from "../api";
import { useT } from "../i18n";
import { Empty, Err, Light, Modal, ReasonModal, Tile, useLoad } from "../ui";
import { can, usePanel } from "./ctx";
import { HrDocs } from "./HrDocs";

export function Onboarding() {
  const { me } = usePanel();
  const t = useT();
  const { data: s, error, reload } = useLoad<any>("/api/onboarding");
  const [open, setOpen] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [score, setScore] = useState<Record<number, string>>({});
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="stack" style={{ gap: 14 }}>
      {s && <div className="grid tiles">
        <Tile label={t("ob_on")} value={s.total} /><Tile label={t("ob_behind")} value={s.behind} />
        <Tile label={t("ob_noMentor")} value={s.no_mentor} /><Tile label={t("ob_noTest")} value={s.no_test} />
        <Tile label={t.l("Boshlash kutilmoqda", "Ждут старта", "Waiting to start")} value={s.waiting} />
      </div>}
      <div className="note">{t("ob_note")}</div>
      <Err e={error || err} />
      <Waiting write={can(me, "onboarding")} onChanged={reload} />
      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}><h2 style={{ margin: 0 }}>{t("ob_plans")}</h2><span className="spacer" />
          {can(me, "onboarding") && <button className="btn primary" onClick={() => setAdding(true)}>{t("ob_addBtn")}</button>}</div>
        {s?.plans.length === 0 && <Empty />}
        <div className="stack">
          {s?.plans.map((p: any) => (
            <div key={p.plan_id} className="person">
              <div className="top" style={{ cursor: "pointer" }} onClick={() => setOpen(open === p.plan_id ? null : p.plan_id)}>
                <Light c={p.light} />
                <div style={{ flex: 1 }}><b>{p.full_name}</b><div className="muted small">{dash(p.position)} · {dash(p.branch)} · {t("c_mentor")} {dash(p.mentor)}</div></div>
                <div className="num small" style={{ textAlign: "right" }}>{t("c_day")} {p.day} · {t("c_stage")} {p.stage}<div><b>{p.progress_pct}%</b> ({p.done}/{p.due})</div></div>
              </div>
              <div className="row small">{Object.entries(p.scores).map(([st, v]: any) => <span key={st} className={`badge ${v.score >= 80 ? "b-ok" : v.score >= 60 ? "b-warn" : "b-bad"}`}>{st}{t("c_dUnit")}: {v.score} {v.label}</span>)}</div>
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
                    <input type="number" min={0} max={100} placeholder={t("ob_testScore")} value={score[p.plan_id] || ""} onChange={(e) => setScore({ ...score, [p.plan_id]: e.target.value })} style={{ width: 160 }} />
                    <button className="btn" disabled={!score[p.plan_id]} onClick={async () => {
                      try { await api(`/api/onboarding/${p.plan_id}/score`, { body: { score: Number(score[p.plan_id]) } }); setScore({ ...score, [p.plan_id]: "" }); reload(); }
                      catch (x: any) { setErr(x.message); }
                    }}>{t("ob_saveScore")} ({t("c_stage")} {p.stage})</button>
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

/** Hired candidates waiting for the employee card + 30/60/90 plan: one click to start, or dismiss with a reason. */
function Waiting({ write, onChanged }: { write: boolean; onChanged: () => void }) {
  const t = useT();
  const { dicts } = usePanel();
  const w = useLoad<any[]>("/api/onboarding/waiting");
  const [start, setStart] = useState<any | null>(null);
  const [dismiss, setDismiss] = useState<any | null>(null);
  const [f, setF] = useState<any>({});
  const [err, setErr] = useState<string | null>(null);
  const done = () => { w.reload(); onChanged(); setStart(null); setDismiss(null); setF({}); };
  if (!w.data?.length) return <Err e={w.error} />;
  return (
    <div className="card">
      <h2>{t.l("Ishga olingan — boshlash kutilmoqda", "Нанятые — ждут старта", "Hired — waiting to start")}</h2>
      <Err e={err} />
      <div className="table-wrap"><table>
        <thead><tr><th>{t("c_name")}</th><th>{t.l("Vakansiya", "Вакансия", "Vacancy")}</th><th>{t("c_branch")}</th>
          <th className="num">{t.l("Kun", "Дней", "Days")}</th><th /></tr></thead>
        <tbody>{w.data.map((h) => (
          <tr key={h.id}><td><b>{h.full_name}</b></td><td className="small">{dash(h.vacancy)}</td><td className="small">{dash(h.branch)}</td>
            <td className="num">{h.days_waiting}</td>
            <td>{write && <div className="row" style={{ flexWrap: "nowrap" }}>
              <button className="btn sm primary" onClick={() => { setStart(h); setF({ branch_id: h.branch_id || "" }); }}>{t.l("Boshlash", "Начать", "Start")}</button>
              <button className="btn sm" onClick={() => setDismiss(h)}>{t.l("Olib tashlash", "Убрать", "Dismiss")}</button></div>}</td></tr>
        ))}</tbody>
      </table></div>
      {start && <Modal title={`${t.l("Boshlash", "Начать", "Start")} · ${start.full_name}`} onClose={() => setStart(null)}>
        <form className="form" onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api(`/api/onboarding/waiting/${start.id}/start`, { body: { mentor: f.mentor || null, start_date: f.start_date || null,
              branch_id: f.branch_id ? Number(f.branch_id) : null, position_id: f.position_id ? Number(f.position_id) : null } });
            done();
          } catch (x: any) { setErr(x.message); }
        }}>
          <label className="field">{t("c_branch")}<select required value={f.branch_id || ""} onChange={(e) => setF({ ...f, branch_id: e.target.value })}>
            <option value="">{t("c_choose")}</option>{dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <label className="field">{t("c_position")}<select value={f.position_id || ""} onChange={(e) => setF({ ...f, position_id: e.target.value })}>
            <option value="">{t.l("Vakansiyadan", "Из вакансии", "From the vacancy")}</option>{dicts.positions.map((p: any) => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
          <label className="field">{t("ob_mentor")}<input value={f.mentor || ""} onChange={(e) => setF({ ...f, mentor: e.target.value })} /></label>
          <label className="field">{t("ob_startDate")}<input type="date" value={f.start_date || ""} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></label>
          <p className="muted small" style={{ margin: 0 }}>{t.l("Xodim kartasi (sinov muddati), 30/60/90 reja va onboarding kursi bitta bosishda yaratiladi.",
            "Карточка сотрудника (испытательный срок), план 30/60/90 и курс создаются одним нажатием.", "The employee card (probation), the 30/60/90 plan and the course are created in one step.")}</p>
          <button className="btn primary">{t.l("Boshlash", "Начать", "Start")}</button>
        </form>
      </Modal>}
      {dismiss && <ReasonModal title={`${t.l("Olib tashlash", "Убрать", "Dismiss")} · ${dismiss.full_name}`} confirmLabel={t.l("Olib tashlash", "Убрать", "Dismiss")}
        onClose={() => setDismiss(null)} onSubmit={async (reason: string) => { await api(`/api/onboarding/waiting/${dismiss.id}/dismiss`, { body: { reason } }); done(); }} />}
    </div>
  );
}

function AddPlan({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const t = useT();
  const emps = useLoad<any[]>("/api/employees");
  const [f, setF] = useState<any>({});
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal title={t("ob_addTitle")} onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try { await api("/api/onboarding", { body: { employee_id: Number(f.employee_id), mentor: f.mentor || null, start_date: f.start_date || null } }); onDone(); onClose(); }
        catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">{t("c_employee")}<select required value={f.employee_id || ""} onChange={(e) => setF({ ...f, employee_id: e.target.value })}>
          <option value="">{t("c_choose")}</option>{emps.data?.filter((e) => e.status !== "fired").map((e) => <option key={e.id} value={e.id}>{e.full_name} — {dash(e.position)}</option>)}</select></label>
        <label className="field">{t("ob_mentor")}<input value={f.mentor || ""} onChange={(e) => setF({ ...f, mentor: e.target.value })} /></label>
        <label className="field">{t("ob_startDate")}<input type="date" value={f.start_date || ""} onChange={(e) => setF({ ...f, start_date: e.target.value })} /></label>
        <p className="muted small" style={{ margin: 0 }}>{t("ob_templateNote")}</p>
        <Err e={err} />
        <button className="btn primary">{t("ob_createPlan")}</button>
      </form>
    </Modal>
  );
}

export function Documents() {
  const { me } = usePanel();
  const t = useT();
  const [days, setDays] = useState(60);
  const { data, error, reload } = useLoad<any[]>(`/api/documents/expiring?days=${days}`, []);
  const [adding, setAdding] = useState(false);
  return (<div className="stack" style={{ gap: 14 }}>
    {can(me, "documents") && <HrDocs />}
    <div className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="muted">{t("ob_expWithin")}</span>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))}>{[30, 60, 90, 180].map((d) => <option key={d} value={d}>{d} {t("c_daysUnit")}</option>)}</select>
        <span className="spacer" />{can(me, "hr.write") && <button className="btn primary" onClick={() => setAdding(true)}>{t("ob_docBtn")}</button>}
      </div>
      <Err e={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>{t("c_employee")}</th><th>{t("c_branch")}</th><th>{t("ob_document")}</th><th>{t("ob_expires")}</th><th className="num">{t("ob_daysLeft")}</th></tr></thead>
        <tbody>{data?.map((d) => (
          <tr key={d.id}><td><b>{d.full_name}</b></td><td>{d.branch}</td><td>{d.title}</td><td className="mono">{d.expires}</td>
            <td className="num"><span className={`badge ${d.expired ? "b-bad" : d.days_left <= 30 ? "b-warn" : ""}`}>{d.expired ? t("ob_expired") : d.days_left}</span></td></tr>
        ))}</tbody>
      </table></div>
      {data?.length === 0 && <Empty text={t("ob_nothingExp")} />}
      {adding && <AddDoc onClose={() => setAdding(false)} onDone={reload} />}
    </div>
  </div>);
}

function AddDoc({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const t = useT();
  const emps = useLoad<any[]>("/api/employees");
  const cfg = useLoad<any>("/api/config/public");
  const [f, setF] = useState<any>({});
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title={t("ob_addDoc")} onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try { await api("/api/documents", { body: { ...f, employee_id: Number(f.employee_id), issued: f.issued || null, expires: f.expires || null } }); onDone(); onClose(); }
        catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">{t("c_employee")}<select required value={f.employee_id || ""} onChange={set("employee_id")}><option value="">{t("c_choose")}</option>
          {emps.data?.map((e) => <option key={e.id} value={e.id}>{e.full_name}</option>)}</select></label>
        <label className="field">{t("c_type")}<select required value={f.doc_type || ""} onChange={set("doc_type")}><option value="">{t("c_choose")}</option>
          {cfg.data?.documents?.map((d: any) => <option key={d.code} value={d.code}>{d.title}</option>)}</select></label>
        <label className="field">{t("ob_number")}<input value={f.number || ""} onChange={set("number")} /></label>
        <label className="field">{t("ob_issued")}<input type="date" value={f.issued || ""} onChange={set("issued")} /></label>
        <label className="field">{t("ob_expires")}<input type="date" value={f.expires || ""} onChange={set("expires")} /></label>
        <Err e={err} />
        <button className="btn primary">{t("save")}</button>
      </form>
    </Modal>
  );
}
