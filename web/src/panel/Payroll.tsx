import { Fragment, useState } from "react";
import { api, money, monthISO } from "../api";
import { Empty, Err, Modal, ReasonModal, Status, Tile, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

const NEXT: Record<string, string> = { calculated: "approved", approved: "paid", paid: "closed" };

export default function Payroll() {
  const { me } = usePanel();
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
        {p?.tabel_closed && <span className="badge">tabel closed</span>}
        {p?.changed_after_calc && <span className="badge b-warn">changed after calculation</span>}
        <span className="spacer" />
        {can(me, "payroll.write") && p && !["approved", "paid", "closed"].includes(p.status) &&
          <button className="btn" onClick={async () => { try { await api(`/api/payroll/${month}/calculate`, { method: "POST" }); reloadAll(); } catch (x: any) { setErr(x.message); } }}>Calculate</button>}
        {can(me, "payroll.approve") && me.branch_scope === null && p && NEXT[p.status] &&
          <button className="btn primary" onClick={() => setStatusTo(NEXT[p.status])}>Mark {NEXT[p.status]}…</button>}
        {canWrite && <button className="btn" onClick={() => setAddEntry(true)}>+ Entry</button>}
        {can(me, "payroll.write") && <label className="btn">Sales CSV<input type="file" accept=".csv" hidden onChange={async (e) => {
          const f = e.target.files?.[0]; if (!f) return;
          const fd = new FormData(); fd.append("file", f);
          try { const r = await api<any>(`/api/payroll/sales/import?month=${month}`, { form: fd }); setUpload(`Imported ${r.imported}, not found ${r.not_found.length}`); reloadAll(); }
          catch (x: any) { setErr(x.message); }
          e.target.value = "";
        }} /></label>}
      </div>
      <Err e={err || table.error} />
      {upload && <div className="note">{upload}</div>}
      <div className="note">Agents never approve payroll: calculated → approved → paid → closed is done by a person with a reason. Tax is not computed (amount “on hand”).</div>
      {p && <div className="grid tiles">
        <Tile label="Fund to pay" value={money(p.fund)} sub={p.amounts_visible ? "known salaries only" : "amounts hidden for your role"} />
        <Tile label="Salary unknown" value={p.unknown_salary} sub="excluded from totals" />
        {pre.data && <Tile label="Pre-check issues" value={pre.data.count} sub={`at risk ${money(pre.data.amount_at_risk)}`} />}
      </div>}
      {pre.data && pre.data.issues.length > 0 && (
        <div className="card">
          <h2>Pre-payout check (Bexruz rules)</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>Type</th><th>Employee</th><th>Branch</th><th>Detail</th><th className="num">At risk</th></tr></thead>
            <tbody>{pre.data.issues.map((i: any, k: number) => (
              <tr key={k}><td><span className="badge b-warn">{i.type}</span></td><td>{i.full_name}</td><td>{i.branch}</td><td>{i.detail}</td><td className="num">{money(i.amount_at_risk)}</td></tr>
            ))}</tbody>
          </table></div>
        </div>
      )}
      {p && (
        <div className="card">
          <h2>Month table</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>Employee</th><th className="num">Hours / norm</th><th className="num">Base</th><th className="num">Accrued</th><th className="num">KPI</th>
              <th className="num">Bonus</th><th className="num">Sales</th><th className="num">Advance</th><th className="num">Penalty</th><th className="num">To pay</th></tr></thead>
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
          <p className="muted small">Click a row to see where each number comes from.</p>
        </div>
      )}
      <div className="card">
        <h2>Entries (advance · bonus · penalty · warning)</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>Employee</th><th>Kind</th><th className="num">Amount</th><th>Reason</th><th>Author</th><th /></tr></thead>
          <tbody>{entries.data?.map((x) => (
            <tr key={x.id} style={x.cancelled ? { textDecoration: "line-through", opacity: .6 } : undefined}>
              <td>{names[x.employee_id] || `#${x.employee_id}`}</td><td><span className="badge">{x.kind}</span></td><td className="num">{money(x.amount)}</td>
              <td>{x.reason}{x.cancel_reason && <div className="muted small">cancelled: {x.cancel_reason}</div>}</td><td className="small">{x.author}</td>
              <td>{canWrite && !x.cancelled && <button className="btn sm" onClick={() => setCancelId(x.id)}>Cancel</button>}</td>
            </tr>
          ))}</tbody>
        </table></div>
        {entries.data?.length === 0 && <Empty />}
      </div>
      {statusTo && <ReasonModal title={`Mark ${month} as ${statusTo}`} confirmLabel={statusTo} onClose={() => setStatusTo(null)}
        onSubmit={async (reason) => { await api(`/api/payroll/${month}/status`, { body: { status: statusTo, reason } }); reloadAll(); }} />}
      {cancelId && <ReasonModal title="Cancel entry (it stays visible, crossed out)" onClose={() => setCancelId(null)}
        onSubmit={async (reason) => { await api(`/api/payroll/entries/${cancelId}/cancel`, { body: { reason } }); reloadAll(); }} />}
      {addEntry && p && <EntryModal month={month} rows={p.rows} onClose={() => setAddEntry(false)} onDone={reloadAll} />}
    </div>
  );
}

function EntryModal({ month, rows, onClose, onDone }: { month: string; rows: any[]; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState<any>({ kind: "advance", employee_id: rows[0]?.employee_id, amount: "", reason: "" });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title="New payroll entry" onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try { await api("/api/payroll/entries", { body: { ...f, month, employee_id: Number(f.employee_id), amount: Number(f.amount || 0) } }); onDone(); onClose(); }
        catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">Employee<select value={f.employee_id} onChange={set("employee_id")}>{rows.map((r) => <option key={r.employee_id} value={r.employee_id}>{r.full_name}</option>)}</select></label>
        <label className="field">Kind<select value={f.kind} onChange={set("kind")}>
          {["advance", "bonus", "penalty", "other", "warning", "kpi"].map((k) => <option key={k}>{k}</option>)}</select></label>
        {f.kind !== "warning" && <label className="field">{f.kind === "kpi" ? "KPI score (0..120)" : "Amount (UZS)"}<input type="number" min={0} value={f.amount} onChange={set("amount")} required /></label>}
        <label className="field">Reason<textarea required minLength={3} maxLength={300} value={f.reason} onChange={set("reason")} /></label>
        <Err e={err} />
        <button className="btn primary">Save</button>
      </form>
    </Modal>
  );
}
