import { useState } from "react";
import { api, dash, money } from "../api";
import { tEnum, useT } from "../i18n";
import { Drawer, Empty, Err, Light, Modal, ReasonModal, Status, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

export default function Employees() {
  const { me, dicts } = usePanel();
  const t = useT();
  const [tab, setTab] = useState<"list" | "leads">("list");
  const [q, setQ] = useState("");
  const [branch, setBranch] = useState("");
  const [status, setStatus] = useState("");
  const qs = new URLSearchParams({ q, ...(branch && { branch_id: branch }), ...(status && { status }) }).toString();
  const { data, error, reload } = useLoad<any[]>(`/api/employees?${qs}`, []);
  const [adding, setAdding] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="pills">
        <button className={`pill ${tab === "list" ? "active" : ""}`} onClick={() => setTab("list")}>{t("em_staff")}</button>
        <button className={`pill ${tab === "leads" ? "active" : ""}`} onClick={() => setTab("leads")}>{t("em_leads")}</button>
      </div>
      {tab === "leads" ? <BranchLeads /> : (
        <div className="card">
          <div className="row" style={{ marginBottom: 12 }}>
            <input placeholder={t("search")} value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: "1 1 200px" }} />
            <select value={branch} onChange={(e) => setBranch(e.target.value)}>
              <option value="">{t("allBranches")}</option>
              {dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">{t("em_anyStatus")}</option><option value="probation">{t("st_probation")}</option><option value="active">{t("st_active")}</option><option value="fired">{t("st_fired")}</option>
            </select>
            {can(me, "hr.write") && <button className="btn primary" onClick={() => setAdding(true)}>{t("em_newBtn")}</button>}
          </div>
          <Err e={error} />
          <div className="table-wrap"><table>
            <thead><tr><th>{t("c_name")}</th><th>{t("c_position")}</th><th>{t("c_branch")}</th><th>{t("c_status")}</th><th>{t("em_hiredCol")}</th><th>{t("em_pay")}</th>{me.payroll && <th className="num">{t("c_salary")}</th>}<th>TG</th></tr></thead>
            <tbody>
              {data?.map((e) => (
                <tr key={e.id} className="click" onClick={() => setOpen(e.id)}>
                  <td><b>{e.full_name}</b><div className="muted small">{dash(e.phone)}</div></td>
                  <td>{dash(e.position)}</td><td>{dash(e.branch)}</td><td><Status s={e.status} /></td>
                  <td className="mono small">{dash(e.hire_date)}</td><td className="small">{tEnum(t, "pt_", e.pay_type)} · {e.schedule_code}</td>
                  {me.payroll && <td className="num">{money(e.base_salary)}</td>}
                  <td>{e.telegram_linked ? "✓" : <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
          {data?.length === 0 && <Empty />}
        </div>
      )}
      {adding && <AddEmployee onClose={() => setAdding(false)} onDone={reload} />}
      {open && <EmployeeDrawer id={open} onClose={() => setOpen(null)} onChanged={reload} />}
    </div>
  );
}

function AddEmployee({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { me, dicts } = usePanel();
  const t = useT();
  const [f, setF] = useState<any>({ status: "probation", pay_type: "monthly", schedule_code: dicts.schedules[0] || "day_9_18",
    branch_id: dicts.branches[0]?.id, hire_date: new Date().toISOString().slice(0, 10) });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title={t("em_newTitle")} onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api("/api/employees", { body: { ...f, branch_id: Number(f.branch_id), position_id: f.position_id ? Number(f.position_id) : null,
            base_salary: f.base_salary ? Number(f.base_salary) : null, leave_balance_days: f.leave_balance_days ? Number(f.leave_balance_days) : null } });
          onDone(); onClose();
        } catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">{t("em_fullName")}<input required minLength={3} value={f.full_name || ""} onChange={set("full_name")} /></label>
        <label className="field">{t("c_phone")}<input value={f.phone || ""} onChange={set("phone")} placeholder="+998…" /></label>
        <label className="field">{t("c_branch")}<select value={f.branch_id} onChange={set("branch_id")}>{dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
        <label className="field">{t("c_position")}<select value={f.position_id || ""} onChange={set("position_id")}><option value="">—</option>{dicts.positions.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
        <label className="field">{t("em_hireDate")}<input type="date" value={f.hire_date} onChange={set("hire_date")} /></label>
        <label className="field">{t("c_schedule")}<select value={f.schedule_code} onChange={set("schedule_code")}>{dicts.schedules.map((s) => <option key={s}>{s}</option>)}</select></label>
        <label className="field">{t("em_payType")}<select value={f.pay_type} onChange={set("pay_type")}><option value="monthly">{t("pt_monthly")}</option><option value="hourly">{t("pt_hourly")}</option><option value="daily">{t("pt_daily")}</option></select></label>
        {me.payroll && <label className="field">{t("em_baseSalarySom")}<input type="number" min={0} value={f.base_salary || ""} onChange={set("base_salary")} /></label>}
        <label className="field">{t("em_leaveBalDays")}<input type="number" min={0} value={f.leave_balance_days || ""} onChange={set("leave_balance_days")} /></label>
        <Err e={err} />
        <button className="btn primary">{t("c_create")}</button>
      </form>
    </Modal>
  );
}

function EmployeeDrawer({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const { me } = usePanel();
  const t = useT();
  const { data: e, error, reload } = useLoad<any>(`/api/employees/${id}`, [id]);
  const [firing, setFiring] = useState(false);
  return (
    <Drawer onClose={onClose}>
      <Err e={error} />
      {e && (
        <div className="stack" style={{ gap: 16 }}>
          <div>
            <h1>{e.full_name}</h1>
            <div className="row muted" style={{ marginTop: 4 }}>{dash(e.position)} · {dash(e.branch)} {e.region && `· ${e.region}`} <Status s={e.status} /></div>
          </div>
          <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Info k={t("em_hiredCol")} v={e.hire_date} /><Info k={t("em_tenure")} v={e.tenure_days !== null ? `${e.tenure_days} ${t("c_daysUnit")}` : null} />
            <Info k={t("c_schedule")} v={e.schedule} /><Info k={t("em_payType")} v={e.pay_type ? tEnum(t, "pt_", e.pay_type) : e.pay_type} />
            <Info k={t("em_leaveBal")} v={e.leave_balance_days} /><Info k={t("c_phone")} v={e.phone} />
            <Info k="Telegram" v={e.telegram_linked ? t("c_linked") : t("c_notLinked")} />
            {me.payroll && <Info k={t("em_baseSalary")} v={money(e.base_salary)} />}
          </div>
          <div className="card">
            <h2>{t("onboarding")}</h2>
            {e.onboarding ? (
              <div className="stack">
                <div className="row"><Light c={e.onboarding.light} /><b>{t("c_day")} {e.onboarding.day}</b> · {t("c_stage")} {e.onboarding.stage} · {e.onboarding.progress_pct}% · {t("c_mentor")} {dash(e.onboarding.mentor)}</div>
                {e.onboarding.items.map((i: any) => <div key={i.id} className="small">{i.done ? "✅" : "⬜"} [{i.stage}] {i.title}</div>)}
              </div>
            ) : <span className="muted">{t("em_noPlan")}</span>}
          </div>
          <div className="card">
            <h2>{t("documents")}</h2>
            {e.documents.length ? e.documents.map((d: any, i: number) => (
              <div key={i} className="row small"><b>{d.title}</b><span className="spacer" /><span className="mono">{dash(d.expires)}</span>
                {d.days_left !== null && <span className={`badge ${d.days_left < 0 ? "b-bad" : d.days_left < 30 ? "b-warn" : ""}`}>{d.days_left} {t("c_dUnit")}</span>}</div>
            )) : <span className="muted">{t("c_none")}</span>}
          </div>
          <div className="card">
            <h2>{t("requests")}</h2>
            {e.requests.length ? e.requests.map((r: any) => (
              <div key={r.id} className="row small"><b>{r.kind}</b><span className="muted">{dash(r.date_from)}…{dash(r.date_to)}</span><span className="spacer" /><Status s={r.status} /></div>
            )) : <span className="muted">{t("c_none")}</span>}
          </div>
          {can(me, "hr.write") && e.status !== "fired" && <button className="btn danger" onClick={() => setFiring(true)}>{t("em_dismissBtn")}</button>}
        </div>
      )}
      {firing && <ReasonModal title={t("em_dismissTitle")} confirmLabel={t("em_dismiss")} onClose={() => setFiring(false)}
        onSubmit={async (reason) => { await api(`/api/employees/${id}/fire`, { body: { reason } }); reload(); onChanged(); }} />}
    </Drawer>
  );
}

function Info({ k, v }: { k: string; v: unknown }) {
  return <div><div className="muted small">{k}</div><div>{dash(v)}</div></div>;
}

function BranchLeads() {
  const { me, dicts } = usePanel();
  const t = useT();
  const { data, error, reload } = useLoad<any[]>("/api/branch-leads");
  const emps = useLoad<any[]>("/api/employees?status=");
  const [branch, setBranch] = useState<string>(String(dicts.branches[0]?.id || ""));
  const [emp, setEmp] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const editable = can(me, "hr.write") && me.branch_scope === null;
  const name = (id: number) => dicts.branches.find((b) => b.id === id)?.name || `#${id}`;
  return (
    <div className="card stack">
      <p className="muted" style={{ margin: 0 }}>{t("em_leadsNote")}</p>
      <Err e={error || err} />
      <div className="table-wrap"><table>
        <thead><tr><th>{t("c_branch")}</th><th>{t("em_lead")}</th><th>Telegram</th><th /></tr></thead>
        <tbody>{data?.map((l) => (
          <tr key={l.id}><td>{name(l.branch_id)}</td><td>{l.full_name}</td><td>{l.telegram_linked ? `✓ ${t("c_linked")}` : <span className="muted">{t("c_notLinked")}</span>}</td>
            <td>{editable && <button className="btn sm danger" onClick={async () => { await api(`/api/branch-leads/${l.id}`, { method: "DELETE" }); reload(); }}>{t("em_remove")}</button>}</td></tr>
        ))}</tbody>
      </table></div>
      {editable && (
        <div className="row">
          <select value={branch} onChange={(e) => setBranch(e.target.value)}>{dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select>
          <select value={emp} onChange={(e) => setEmp(e.target.value)} style={{ flex: "1 1 200px" }}>
            <option value="">{t("em_chooseEmp")}</option>
            {emps.data?.filter((e) => e.status !== "fired").map((e) => <option key={e.id} value={e.id}>{e.full_name} — {dash(e.position)}</option>)}
          </select>
          <button className="btn primary" disabled={!emp} onClick={async () => {
            try { await api("/api/branch-leads", { body: { branch_id: Number(branch), employee_id: Number(emp) } }); setEmp(""); reload(); }
            catch (x: any) { setErr(x.message); }
          }}>{t("em_assign")}</button>
        </div>
      )}
    </div>
  );
}
