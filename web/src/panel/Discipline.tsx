import { useState } from "react";
import { api, dash, money, monthISO } from "../api";
import { useT } from "../i18n";
import { Empty, Err, Modal, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

type T = ReturnType<typeof useT>;
const windowName = (t: T, w: string) => ({
  month: t.l("shu oy ichida", "в этом месяце", "this month"),
  all_time: t.l("boshlanish sanasidan", "с даты начала", "since start date"),
  per_case: t.l("har holat — jarima", "каждый случай — штраф", "every case is a fine"),
} as Record<string, string>)[w] || w;

/** Warnings -> fines. The rule list comes from company.yaml; only admins edit texts and amounts here. */
export default function Discipline() {
  const t = useT();
  const { me } = usePanel();
  const rules = useLoad<any>("/api/discipline/rules");
  const [month, setMonth] = useState(monthISO());
  const cases = useLoad<any[]>(`/api/discipline/cases?month=${month}`, [month]);
  const [edit, setEdit] = useState<any | null>(null);
  const [applying, setApplying] = useState(false);
  const write = can(me, "hr.write") || can(me, "payroll.write");
  return (
    <div className="stack" style={{ gap: 14 }}>
      <Err e={rules.error || cases.error} />
      <div className="note">{t.l(
        "Qoidani odam qo'llaydi. Oynadagi birinchi holatlar — ogohlantirish, keyin jarima. Yozilgan jarima summasi qoida keyin o'zgarsa ham o'zgarmaydi.",
        "Правило применяет человек. Первые случаи в окне — предупреждения, затем штраф. Записанный штраф сохраняет сумму, даже если правило потом изменят.",
        "A person applies a rule. The first cases inside the window are warnings, then a fine. A recorded fine keeps its amount even if the rule changes later.")}</div>
      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}><h2 style={{ margin: 0 }}>{t.l("Qoidalar", "Правила", "Rules")}</h2><span className="spacer" />
          {write && <button className="btn primary" onClick={() => setApplying(true)}>{t.l("Qoidani qo'llash", "Применить правило", "Apply a rule")}</button>}</div>
        <div className="table-wrap"><table>
          <thead><tr><th>{t.l("Qoida", "Правило", "Rule")}</th><th>{t.l("Hisoblash", "Подсчёт", "Counting")}</th>
            <th className="num">{t.l("Avval ogohlantirish", "Сначала предупреждений", "Warnings first")}</th><th className="num">{t.l("Jarima", "Штраф", "Fine")}</th>
            <th className="num">{t.l("Qo'shimcha", "Доп. сумма", "Extra")}</th><th>{t.l("Boshlanish", "С даты", "From")}</th><th /></tr></thead>
          <tbody>{rules.data?.rules.map((r: any) => (
            <tr key={r.id}><td><b>{r.title}</b><div className="muted small">{r.text || "—"}</div>{r.note && <div className="small">{r.note}</div>}</td>
              <td className="small">{windowName(t, r.window)}</td><td className="num">{r.window === "per_case" ? "—" : r.warnings_before_fine}</td>
              <td className="num">{money(r.fine_amount)}</td><td className="num">{money(r.extra_amount)}</td><td className="mono small">{dash(r.starts_on)}</td>
              <td>{rules.data.can_edit && <button className="btn sm" onClick={() => setEdit(r)}>{t.l("Tahrirlash", "Изменить", "Edit")}</button>}</td></tr>
          ))}</tbody>
        </table></div>
        {rules.data?.rules.length === 0 && <Empty text="company.yaml → discipline.rules" />}
      </div>
      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}><h2 style={{ margin: 0 }}>{t.l("Holatlar", "Случаи", "Cases")}</h2><span className="spacer" />
          <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></div>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("c_employee")}</th><th>{t.l("Qoida", "Правило", "Rule")}</th><th>{t.l("Natija", "Итог", "Outcome")}</th>
            <th className="num">{t.l("Summa", "Сумма", "Amount")}</th><th>{t.l("Sabab", "Причина", "Reason")}</th><th>{t.l("Kim", "Кто", "By")}</th></tr></thead>
          <tbody>{cases.data?.map((x) => (
            <tr key={x.id} style={x.cancelled ? { opacity: 0.5 } : undefined}><td><b>{x.full_name}</b></td><td>{x.rule}</td>
              <td><span className={`badge ${x.outcome === "fine" ? "b-bad" : "b-warn"}`}>
                {x.outcome === "fine" ? t.l("jarima", "штраф", "fine") : t.l("ogohlantirish", "предупреждение", "warning")}{x.cancelled ? " · ✕" : ""}</span></td>
              <td className="num">{x.outcome === "warning" ? "—" : money(x.amount)}</td><td className="small">{x.reason}</td><td className="small">{x.author}</td></tr>
          ))}</tbody>
        </table></div>
        {cases.data?.length === 0 && <Empty />}
      </div>
      {edit && <EditRule rule={edit} windows={rules.data.windows} onClose={() => setEdit(null)} onDone={rules.reload} />}
      {applying && <ApplyRule rules={rules.data?.rules || []} onClose={() => setApplying(false)} onDone={cases.reload} />}
    </div>
  );
}

function EditRule({ rule, windows, onClose, onDone }: { rule: any; windows: string[]; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const [f, setF] = useState<any>({ ...rule });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title={`${t.l("Qoida", "Правило", "Rule")} · ${rule.code}`} onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api(`/api/discipline/rules/${rule.id}`, { method: "PATCH", body: {
            title: f.title, text: f.text, note: f.note, window: f.window, warnings_before_fine: Number(f.warnings_before_fine),
            fine_amount: Number(f.fine_amount), extra_amount: Number(f.extra_amount), starts_on: f.starts_on || null } });
          onDone(); onClose();
        } catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">{t.l("Nomi", "Название", "Title")}<input required minLength={2} value={f.title} onChange={set("title")} /></label>
        <label className="field">{t.l("Qoida matni", "Текст правила", "Rule text")}<textarea rows={3} value={f.text} onChange={set("text")} /></label>
        <label className="field">{t.l("Hisoblash oynasi", "Окно подсчёта", "Counting window")}<select value={f.window} onChange={set("window")}>
          {windows.map((w) => <option key={w} value={w}>{windowName(t, w)}</option>)}</select></label>
        <label className="field">{t.l("Jarimagacha ogohlantirishlar", "Предупреждений до штрафа", "Warnings before a fine")}<input type="number" min={0} max={20} value={f.warnings_before_fine} onChange={set("warnings_before_fine")} /></label>
        <label className="field">{t.l("Jarima summasi", "Сумма штрафа", "Fine amount")}<input type="number" min={0} value={f.fine_amount} onChange={set("fine_amount")} /></label>
        <label className="field">{t.l("Soliq / qo'shimcha summa", "Налог / доп. сумма", "Tax / extra amount")}<input type="number" min={0} value={f.extra_amount} onChange={set("extra_amount")} /></label>
        <label className="field">{t.l("Izoh", "Примечание", "Note")}<input maxLength={300} value={f.note} onChange={set("note")} /></label>
        <label className="field">{t.l("Boshlanish sanasi", "Дата начала", "Start date")}<input type="date" value={f.starts_on || ""} onChange={set("starts_on")} /></label>
        <p className="muted small" style={{ margin: 0 }}>{t.l("Har bir o'zgarish audit jurnaliga oldingi va yangi qiymat bilan yoziladi.",
          "Каждое изменение пишется в журнал аудита со значениями до и после.", "Every change is written to the audit log with the values before and after.")}</p>
        <Err e={err} />
        <button className="btn primary">{t("save")}</button>
      </form>
    </Modal>
  );
}

function ApplyRule({ rules, onClose, onDone }: { rules: any[]; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const emps = useLoad<any[]>("/api/employees");
  const [f, setF] = useState<any>({ month: monthISO() });
  const [res, setRes] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title={t.l("Qoidani qo'llash", "Применить правило", "Apply a rule")} onClose={onClose}>
      {res ? (
        <div className="stack">
          <div className="note">{res.full_name}: <b>{res.outcome === "fine" ? t.l("jarima", "штраф", "fine") : t.l("ogohlantirish", "предупреждение", "warning")}</b>
            {res.outcome === "fine" && res.amount !== null ? ` · ${money(res.amount)}` : ""} ({t.l("oynadagi oldingi holatlar", "прежних случаев в окне", "earlier cases in the window")}: {res.prior_count})</div>
          <button className="btn primary" onClick={onClose}>OK</button>
        </div>
      ) : (
        <form className="form" onSubmit={async (e) => {
          e.preventDefault();
          try { setRes(await api("/api/discipline/apply", { body: { employee_id: Number(f.employee_id), rule_id: Number(f.rule_id), month: f.month, reason: f.reason } })); onDone(); }
          catch (x: any) { setErr(x.message); }
        }}>
          <label className="field">{t("c_employee")}<select required value={f.employee_id || ""} onChange={set("employee_id")}><option value="">{t("c_choose")}</option>
            {emps.data?.filter((e) => e.status !== "fired").map((e) => <option key={e.id} value={e.id}>{e.full_name} — {dash(e.branch)}</option>)}</select></label>
          <label className="field">{t.l("Qoida", "Правило", "Rule")}<select required value={f.rule_id || ""} onChange={set("rule_id")}><option value="">{t("c_choose")}</option>
            {rules.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}</select></label>
          <label className="field">{t.l("Oy", "Месяц", "Month")}<input type="month" required value={f.month} onChange={set("month")} /></label>
          <label className="field">{t.l("Sabab", "Причина", "Reason")}<textarea rows={2} required minLength={3} value={f.reason || ""} onChange={set("reason")} /></label>
          <Err e={err} />
          <button className="btn primary">{t.l("Qo'llash", "Применить", "Apply")}</button>
        </form>
      )}
    </Modal>
  );
}
