import { useState } from "react";
import { api, dash } from "../api";
import { tEnum, useT } from "../i18n";
import { Empty, Err, Light, Modal, Status, useLoad } from "../ui";
import { can, usePanel } from "./ctx";
import { CandidateHiring, SlotsCard } from "./Hiring";
import { NewVacancy, VacancyEditor } from "./VacancyEditor";

const CRIT: Record<string, string> = { role_fit: "crit_role_fit", specifics: "crit_specifics", communication: "crit_communication", motivation: "crit_motivation" };

export default function Recruiting() {
  const { me } = usePanel();
  const t = useT();
  const vac = useLoad<any[]>("/api/vacancies");
  const [vid, setVid] = useState<number | null>(null);
  const cands = useLoad<any[]>(`/api/candidates${vid ? `?vacancy_id=${vid}` : ""}`, []);
  const [drafting, setDrafting] = useState(false);
  const [aiNew, setAiNew] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [filter, setFilter] = useState("active");
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
        <div className="row" style={{ marginBottom: 10 }}><h2 style={{ margin: 0 }}>{t("rc_vacancies")}</h2><span className="spacer" />
          {!location.pathname.startsWith("/rauf") && <a className="btn" href="/rauf">{t("rc_raufPanel")}</a>}
          <select className="ctl" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="active">{t.l("Qoralama + ochiq", "Черновики + открытые", "Drafts + open")}</option>
            <option value="open">{t.l("Ochiq", "Открытые", "Open")}</option><option value="draft">{t.l("Qoralama", "Черновики", "Drafts")}</option>
            <option value="closed">{t.l("Yopilgan", "Закрытые", "Closed")}</option><option value="tpl">{t.l("Shablonlar", "Шаблоны", "Templates")}</option>
            <option value="all">{t("all")}</option></select>
          {write && <button className="btn" onClick={() => setDrafting(true)}>{t("rc_draftBtn")}</button>}
          {write && <button className="btn primary" onClick={() => setAiNew(true)}>✨ {t.l("Agent bilan yozish", "Написать с агентом", "Write with agent")}</button>}</div>
        <div className="table-wrap"><table>
          <thead><tr><th /><th>{t("c_title")}</th><th>{t("c_branch")}</th><th>{t("c_salary")}</th><th>{t("c_schedule")}</th><th>{t("c_status")}</th><th className="num">SLA</th><th /></tr></thead>
          <tbody>{vac.data?.filter((v) => filter === "all" || (filter === "tpl" ? v.is_template : filter === "active" ? v.status !== "closed" : v.status === filter)).map((v) => (
            <tr key={v.id} className="click" onClick={() => setVid(vid === v.id ? null : v.id)} style={vid === v.id ? { outline: "2px solid var(--primary)" } : undefined}>
              <td><Light c={v.light} /></td><td><b>{v.title}</b>{v.public && <span className="badge b-info" style={{ marginLeft: 6 }}>web</span>}{v.is_template && <span className="badge" style={{ marginLeft: 6 }}>tpl</span>}</td><td>{dash(v.branch)}</td><td className="small">{dash(v.salary_text)}</td>
              <td className="small">{dash(v.schedule_text)}</td><td><Status s={v.status} /></td>
              <td className="num">{v.days_open !== null && v.days_open !== undefined ? `${v.days_open}/${v.sla_days}${t("c_dUnit")}` : `${v.sla_days}${t("c_dUnit")}`}</td>
              <td onClick={(e) => e.stopPropagation()} className="row">
                <button className="btn sm" onClick={() => setPreview(v)}>{t("rc_ad")}</button>
                {write && <button className="btn sm" onClick={() => setEditId(v.id)}>{t("edit")}</button>}
                {write && v.status === "draft" && <button className="btn sm primary" onClick={async () => {
                  try { await api(`/api/vacancies/${v.id}/open`, { method: "POST" }); vac.reload(); } catch (x: any) { setErr(x.message); }
                }}>{t("rc_open")}</button>}
              </td>
            </tr>
          ))}</tbody>
        </table></div>
        {vac.data?.length === 0 && <Empty />}
      </div>
      <div className="card">
        <h2>{t("rc_candidates")} {vid && <span className="muted small">{t("rc_filtered")}</span>}</h2>
        <div className="note" style={{ marginBottom: 10 }}>{t("rc_noAutoReject")}</div>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("c_name")}</th><th>{t("c_vacancy")}</th><th className="num">{t("c_score")}</th><th>{t("rc_label")}</th><th>{t("c_status")}</th><th>{t("c_source")}</th></tr></thead>
          <tbody>{cands.data?.map((c) => (
            <tr key={c.id} className="click" onClick={() => setCand(c)}>
              <td><b>{c.full_name}</b><div className="muted small">{dash(c.phone)}</div></td><td>{dash(c.vacancy)}</td>
              <td className="num"><b>{dash(c.score)}</b></td><td>{c.label ? <span className={`badge ${c.label === "strong" ? "b-ok" : c.label === "medium" ? "b-warn" : "b-bad"}`}>{tEnum(t, "lbl_", c.label)}</span> : <span className="muted small">{t("rc_evalManually")}</span>}</td>
              <td><Status s={c.status} /></td><td className="small">{c.source}</td>
            </tr>
          ))}</tbody>
        </table></div>
        {cands.data?.length === 0 && <Empty />}
      </div>
      <SlotsCard write={write} />
      {preview && <Modal title={`${t("rc_ad")} · ${preview.title}`} onClose={() => setPreview(null)}>
        <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font)", background: "var(--surface-2)", padding: 12, borderRadius: 10, margin: 0 }}>{preview.ad_text}</pre>
      </Modal>}
      {cand && <Modal title={cand.full_name} onClose={() => setCand(null)}>
        <div className="stack">
          <div className="row"><Status s={cand.status} /><b className="num">{dash(cand.score)}</b><span className="muted">{cand.label ? tEnum(t, "lbl_", cand.label) : dash(cand.label)}</span></div>
          {Object.keys(CRIT).map((k) => cand.breakdown?.[k] && (
            <div key={k}><div className="row small"><b>{t(CRIT[k])}</b><span className="spacer" /><span className="num">{cand.breakdown[k].score}</span></div>
              <div className="muted small">{cand.breakdown[k].comment || t("rc_noComment")}</div></div>
          ))}
          {cand.answers?.length > 0 && <div className="stack small">{cand.answers.map((a: any, i: number) => <div key={i}><b>{a.q}</b><div>{a.a}</div></div>)}</div>}
          {write && <div className="row">
            <button className="btn" onClick={() => setStatus(cand.id, "shortlist")}>{t("rc_shortlistBtn")}</button>
            <button className="btn primary" onClick={() => setStatus(cand.id, "hired")}>{t("rc_hiredBtn")}</button>
            <button className="btn danger" onClick={() => setStatus(cand.id, "rejected")}>{t("reject")}</button>
          </div>}
          <CandidateHiring cand={cand} write={write} onChanged={cands.reload} />
        </div>
      </Modal>}
      {drafting && <DraftVacancy onClose={() => setDrafting(false)} onDone={vac.reload} />}
      {aiNew && <NewVacancy onClose={() => setAiNew(false)} onOpen={(x) => { setAiNew(false); vac.reload(); setEditId(x.id); }} />}
      {editId && <VacancyEditor id={editId} onClose={() => setEditId(null)} onChanged={vac.reload} />}
    </div>
  );
}

function DraftVacancy({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { dicts } = usePanel();
  const t = useT();
  const [f, setF] = useState<any>({ title: "", requirements: "" });
  const [res, setRes] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title={t("rc_draftTitle")} onClose={onClose}>
      {res ? (
        <div className="stack">
          {res.missing.length > 0 ? <div className="error">{t("rc_missing")} {res.missing.join(", ")}</div> : <div className="note">{t("rc_ready")}</div>}
          <pre style={{ whiteSpace: "pre-wrap", fontFamily: "var(--font)", background: "var(--surface-2)", padding: 12, borderRadius: 10, margin: 0 }}>{res.preview}</pre>
          <button className="btn primary" onClick={onClose}>{t("rc_done")}</button>
        </div>
      ) : (
        <form className="form" onSubmit={async (e) => {
          e.preventDefault();
          try {
            setRes(await api("/api/vacancies", { body: { ...f, branch_id: f.branch_id ? Number(f.branch_id) : null, position_code: f.position_code || null } }));
            onDone();
          } catch (x: any) { setErr(x.message); }
        }}>
          <label className="field">{t("c_title")}<input required value={f.title} onChange={set("title")} /></label>
          <label className="field">{t("c_position")}<select value={f.position_code || ""} onChange={set("position_code")}><option value="">—</option>{dicts.positions.map((p) => <option key={p.code} value={p.code}>{p.title}</option>)}</select></label>
          <label className="field">{t("c_branch")}<select value={f.branch_id || ""} onChange={set("branch_id")}><option value="">—</option>{dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <label className="field">{t("rc_salaryLabel")}<input value={f.salary_text || ""} onChange={set("salary_text")} /></label>
          <label className="field">{t("c_schedule")}<input value={f.schedule_text || ""} onChange={set("schedule_text")} placeholder="24/48, 2/2, 09:00–18:00" /></label>
          <label className="field">{t("rc_requirements")}<textarea rows={3} value={f.requirements} onChange={set("requirements")} /></label>
          <Err e={err} />
          <button className="btn primary">{t("rc_createDraft")}</button>
        </form>
      )}
    </Modal>
  );
}
