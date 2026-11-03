import { Check } from "lucide-react";
import { useState } from "react";
import { api, dash, download } from "../api";
import { useT } from "../i18n";
import { Empty, Err, Modal, useLoad } from "../ui";

/** HR documents from templates: issue for an employee -> PDF; templates are editable text with {fields}. */
export function HrDocs() {
  const t = useT();
  const docs = useLoad<any[]>("/api/hr-docs", []);
  const tpls = useLoad<any[]>("/api/hr-docs/templates", []);
  const [issuing, setIssuing] = useState(false);
  const [editTpl, setEditTpl] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 10 }}><h2 style={{ margin: 0 }}>{t.l("HR hujjatlar (PDF)", "HR-документы (PDF)", "HR documents (PDF)")}</h2>
        <span className="spacer" />
        <select className="ctl" value="" onChange={(e) => setEditTpl(tpls.data?.find((x) => String(x.id) === e.target.value) || null)}>
          <option value="">{t.l("Shablonni tahrirlash…", "Править шаблон…", "Edit template…")}</option>
          {tpls.data?.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}</select>
        <button className="btn primary" onClick={() => setIssuing(true)}>+ {t.l("Hujjat yaratish", "Создать документ", "New document")}</button></div>
      <Err e={err || docs.error || tpls.error} />
      <div className="table-wrap"><table>
        <thead><tr><th>№</th><th>{t.l("Hujjat", "Документ", "Document")}</th><th>{t.l("Xodim", "Сотрудник", "Employee")}</th>
          <th>{t.l("Bo'sh maydonlar", "Пустые поля", "Blank fields")}</th><th>{t.l("Sana", "Дата", "Date")}</th><th /></tr></thead>
        <tbody>{docs.data?.map((d) => (
          <tr key={d.id}><td className="num"><b>{d.number}</b></td><td>{d.title}</td><td>{dash(d.employee)}</td>
            <td className="small">{d.missing.length ? <span className="badge b-warn">{d.missing.join(", ")}</span> : <span className="badge b-ok"><Check className="ic inl" size={14} aria-hidden="true" /></span>}</td>
            <td className="small">{new Date(d.created_at).toLocaleDateString("ru-RU")}</td>
            <td><button className="btn sm" onClick={() => download(`/api/hr-docs/${d.id}/pdf`, `${d.number}.pdf`).catch((x) => setErr(x.message))}>⤓ PDF</button></td></tr>
        ))}</tbody>
      </table></div>
      {docs.data?.length === 0 && <Empty />}
      {issuing && <IssueDoc tpls={tpls.data || []} onClose={() => setIssuing(false)} onDone={(d) => {
        setIssuing(false); docs.reload(); download(`/api/hr-docs/${d.id}/pdf`, `${d.number}.pdf`).catch((x) => setErr(x.message));
      }} />}
      {editTpl && <EditTpl tpl={editTpl} onClose={() => setEditTpl(null)} onDone={() => { setEditTpl(null); tpls.reload(); }} />}
    </div>
  );
}

const AUTO = new Set(["company", "today", "number", "full_name", "position", "department", "branch", "hire_date", "phone", "salary",
  "hr_name", "director", "probation"]);

function IssueDoc({ tpls, onClose, onDone }: { tpls: any[]; onClose: () => void; onDone: (d: any) => void }) {
  const t = useT();
  const emps = useLoad<any>("/api/employees");
  const list: any[] = Array.isArray(emps.data) ? emps.data : emps.data?.items || [];
  const [tid, setTid] = useState<string>(tpls[0] ? String(tpls[0].id) : "");
  const [eid, setEid] = useState("");
  const [extra, setExtra] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const tpl = tpls.find((x) => String(x.id) === tid);
  const own = (tpl?.fields || []).filter((f: string) => !AUTO.has(f));
  return (
    <Modal title={t.l("Hujjat yaratish", "Создать документ", "New document")} onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try { onDone(await api("/api/hr-docs", { body: { template_id: Number(tid), employee_id: eid ? Number(eid) : null, extra } })); }
        catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">{t.l("Shablon", "Шаблон", "Template")}<select value={tid} onChange={(e) => { setTid(e.target.value); setExtra({}); }}>
          {tpls.filter((x) => x.active).map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}</select></label>
        <label className="field">{t.l("Xodim", "Сотрудник", "Employee")}<select required value={eid} onChange={(e) => setEid(e.target.value)}>
          <option value="">—</option>{list.map((x) => <option key={x.id} value={x.id}>{x.full_name}</option>)}</select></label>
        {own.map((f: string) => <label key={f} className="field">{f}<input value={extra[f] || ""} onChange={(e) => setExtra({ ...extra, [f]: e.target.value })} /></label>)}
        <div className="note small">{t.l("Kartadagi ma'lumotlar o'zi qo'yiladi. Noma'lumi bo'sh chiziq bo'lib qoladi.",
          "Данные из карточки подставятся сами. Неизвестное останется пустой строкой.", "Card data is filled in; unknown fields stay blank.")}</div>
        <Err e={err} />
        <button className="btn primary">⤓ PDF</button>
      </form>
    </Modal>
  );
}

function EditTpl({ tpl, onClose, onDone }: { tpl: any; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const [f, setF] = useState({ title: tpl.title, body: tpl.body, active: tpl.active });
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal title={tpl.title} onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try { await api(`/api/hr-docs/templates/${tpl.id}`, { method: "PATCH", body: f }); onDone(); } catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">{t("c_title")}<input required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
        <label className="field">{t.l("Matn", "Текст", "Text")}<textarea rows={14} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></label>
        <div className="muted small">{t.l("Maydonlar", "Поля", "Fields")}: {"{full_name} {position} {department} {branch} {hire_date} {today} {number} {company}"}</div>
        <Err e={err} />
        <button className="btn primary">{t("save")}</button>
      </form>
    </Modal>
  );
}
