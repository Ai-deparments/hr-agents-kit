import { Fragment, useState } from "react";
import { api, money, monthISO } from "../api";
import { tEnum, useT } from "../i18n";
import { Empty, Err, Modal, ReasonModal, Status, Tile, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

const NEXT: Record<string, string> = { calculated: "approved", approved: "paid", paid: "closed" };

export default function Payroll() {
  const { me } = usePanel();
  const t = useT();
  const [month, setMonth] = useState(monthISO());
  const table = useLoad<any>(`/api/payroll?month=${month}`, []);
  const pre = useLoad<any>(can(me, "payroll.read") ? `/api/payroll/${month}/precheck` : null, []);
  const entries = useLoad<any[]>(`/api/payroll/entries?month=${month}`, []);
  const [open, setOpen] = useState<number | null>(null);
  const [statusTo, setStatusTo] = useState<string | null>(null);
  const [addEntry, setAddEntry] = useState(false);
  const [cancelId, setCancelId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [upload, setUpload] = useState<string | null>(null);
  const p = table.data;
  const reloadAll = () => { table.reload(); pre.reload(); entries.reload(); };
  const names: Record<number, string> = Object.fromEntries((p?.rows || []).map((r: any) => [r.employee_id, r.full_name]));
  const canWrite = can(me, "payroll.write") || can(me, "hr.write");

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="row">
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
        {p && <Status s={p.status} />}
        {p?.tabel_closed && <span className="badge">{t("pr_tabelClosed")}</span>}
        {p?.changed_after_calc && <span className="badge b-warn">{t("pr_changedAfter")}</span>}
        <span className="spacer" />
        {can(me, "payroll.write") && p && !["approved", "paid", "closed"].includes(p.status) &&
          <button className="btn" onClick={async () => { try { await api(`/api/payroll/${month}/calculate`, { method: "POST" }); reloadAll(); } catch (x: any) { setErr(x.message); } }}>{t("pr_calculate")}</button>}
        {can(me, "payroll.approve") && me.branch_scope === null && p && NEXT[p.status] &&
          <button className="btn primary" onClick={() => setStatusTo(NEXT[p.status])}>{t("pr_markAs")} {tEnum(t, "st_", NEXT[p.status])}…</button>}
        {canWrite && <button className="btn" onClick={() => setAddEntry(true)}>{t("pr_entry")}</button>}
        {can(me, "payroll.write") && <label className="btn">{t("pr_salesCsv")}<input type="file" accept=".csv" hidden onChange={async (e) => {
          const f = e.target.files?.[0]; if (!f) return;
          const fd = new FormData(); fd.append("file", f);
          try { const r = await api<any>(`/api/payroll/sales/import?month=${month}`, { form: fd }); setUpload(`${t("pr_imported")} ${r.imported}, ${t("pr_notFound")} ${r.not_found.length}`); reloadAll(); }
          catch (x: any) { setErr(x.message); }
          e.target.value = "";
        }} /></label>}
      </div>
      <Err e={err || table.error} />
      {upload && <div className="note">{upload}</div>}
      <div className="note">{t("pr_note")}</div>
      {p && <div className="grid tiles">
        <Tile label={t("pr_fund")} value={money(p.fund)} sub={p.amounts_visible ? t("pr_knownOnly") : t("pr_hidden")} />
        <Tile label={t("pr_salaryUnknown")} value={p.unknown_salary} sub={t("pr_excluded")} />
        {pre.data && <Tile label={t("pr_preIssues")} value={pre.data.count} sub={`${t("pr_atRisk")} ${money(pre.data.amount_at_risk)}`} />}
      </div>}
      {pre.data && pre.data.issues.length > 0 && (
        <div className="card">
          <h2>{t("pr_precheck")}</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>{t("c_type")}</th><th>{t("c_employee")}</th><th>{t("c_branch")}</th><th>{t("c_detail")}</th><th className="num">{t("pr_atRiskCol")}</th></tr></thead>
            <tbody>{pre.data.issues.map((i: any, k: number) => (
              <tr key={k}><td><span className="badge b-warn">{i.type}</span></td><td>{i.full_name}</td><td>{i.branch}</td><td>{i.detail}</td><td className="num">{money(i.amount_at_risk)}</td></tr>
            ))}</tbody>
          </table></div>
        </div>
      )}
      {p && (
        <div className="card">
          <h2>{t("pr_monthTable")}</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>{t("c_employee")}</th><th className="num">{t("pr_hoursNorm")}</th><th className="num">{t("pr_base")}</th><th className="num">{t("pr_accrued")}</th><th className="num">KPI</th>
              <th className="num">{t("bonus")}</th><th className="num">{t("pr_sales")}</th><th className="num">{t("advance")}</th><th className="num">{t("penalty")}</th><th className="num">{t("pr_toPay")}</th></tr></thead>
            <tbody>{p.rows.map((r: any) => (
              <Fragment key={r.employee_id}>
                <tr className="click" onClick={() => setOpen(open === r.employee_id ? null : r.employee_id)}>
                  <td><b>{r.full_name}</b><div className="muted small">{r.branch} · {r.position}{r.warnings ? ` · ⚠ ${r.warnings}` : ""}</div></td>
                  <td className="num">{r.worked_hours} / {r.norm_hours}</td><td className="num">{money(r.base)}</td><td className="num">{money(r.accrued)}</td>
                  <td className="num">{money(r.kpi)}</td><td className="num">{money(r.bonus)}</td><td className="num">{money(r.sales_bonus)}</td>
                  <td className="num">{money(r.advance)}</td><td className="num">{money(r.penalty === null ? null : (r.penalty || 0) + (r.late_penalty || 0))}</td>
                  <td className="num"><b>{money(r.total)}</b></td>
                </tr>
                {open === r.employee_id && r.explain?.length > 0 && (
                  <tr><td colSpan={10} className="mono small" style={{ background: "var(--surface-2)" }}>{r.explain.map((l: string, i: number) => <div key={i}>{l}</div>)}</td></tr>
                )}
              </Fragment>
            ))}</tbody>
          </table></div>
          <p className="muted small">{t("pr_clickRow")}</p>
        </div>
      )}
      <div className="card">
        <h2>{t("pr_entries")}</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("c_employee")}</th><th>{t("c_kind")}</th><th className="num">{t("c_amount")}</th><th>{t("reason")}</th><th>{t("c_author")}</th><th /></tr></thead>
          <tbody>{entries.data?.map((x) => (
            <tr key={x.id} style={x.cancelled ? { textDecoration: "line-through", opacity: .6 } : undefined}>
              <td>{names[x.employee_id] || `#${x.employee_id}`}</td><td><span className="badge">{tEnum(t, "pk_", x.kind)}</span></td><td className="num">{money(x.amount)}</td>
              <td>{x.reason}{x.cancel_reason && <div className="muted small">{t("pr_cancelled")} {x.cancel_reason}</div>}</td><td className="small">{x.author}</td>
              <td>{canWrite && !x.cancelled && <button className="btn sm" onClick={() => setCancelId(x.id)}>{t("cancel")}</button>}</td>
            </tr>
          ))}</tbody>
        </table></div>
        {entries.data?.length === 0 && <Empty />}
      </div>
      {statusTo && <ReasonModal title={`${t("pr_markAs")} ${tEnum(t, "st_", statusTo)} · ${month}`} confirmLabel={tEnum(t, "st_", statusTo)} onClose={() => setStatusTo(null)}
        onSubmit={async (reason) => { await api(`/api/payroll/${month}/status`, { body: { status: statusTo, reason } }); reloadAll(); }} />}
      {cancelId && <ReasonModal title={t("pr_cancelEntry")} onClose={() => setCancelId(null)}
        onSubmit={async (reason) => { await api(`/api/payroll/entries/${cancelId}/cancel`, { body: { reason } }); reloadAll(); }} />}
      {addEntry && p && <EntryModal month={month} rows={p.rows} onClose={() => setAddEntry(false)} onDone={reloadAll} />}
    </div>
  );
}

function EntryModal({ month, rows, onClose, onDone }: { month: string; rows: any[]; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const [f, setF] = useState<any>({ kind: "advance", employee_id: rows[0]?.employee_id, amount: "", reason: "" });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title={t("pr_newEntry")} onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try { await api("/api/payroll/entries", { body: { ...f, month, employee_id: Number(f.employee_id), amount: Number(f.amount || 0) } }); onDone(); onClose(); }
        catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">{t("c_employee")}<select value={f.employee_id} onChange={set("employee_id")}>{rows.map((r) => <option key={r.employee_id} value={r.employee_id}>{r.full_name}</option>)}</select></label>
        <label className="field">{t("c_kind")}<select value={f.kind} onChange={set("kind")}>
          {["advance", "bonus", "penalty", "other", "warning", "kpi"].map((k) => <option key={k} value={k}>{tEnum(t, "pk_", k)}</option>)}</select></label>
        {f.kind !== "warning" && <label className="field">{f.kind === "kpi" ? t("pr_kpiScore") : t("pr_amountSom")}<input type="number" min={0} value={f.amount} onChange={set("amount")} required /></label>}
        <label className="field">{t("reason")}<textarea required minLength={3} maxLength={300} value={f.reason} onChange={set("reason")} /></label>
        <Err e={err} />
        <button className="btn primary">{t("save")}</button>
      </form>
    </Modal>
  );
}
