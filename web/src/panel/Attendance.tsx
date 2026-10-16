import { useState } from "react";
import { api, dash, download, monthISO, shiftDay, todayISO } from "../api";
import { useT } from "../i18n";
import { Empty, Err, ReasonModal, Status, Tile, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

function BranchSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { dicts } = usePanel();
  const t = useT();
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t("allBranches")}</option>
      {dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
    </select>
  );
}

export function Attendance() {
  const t = useT();
  const [day, setDay] = useState(todayISO());
  const [branch, setBranch] = useState("");
  const [only, setOnly] = useState("");
  const { data: s, error } = useLoad<any>(`/api/attendance/day?day=${day}${branch ? `&branch_id=${branch}` : ""}`, []);
  const rows = (s?.rows || []).filter((r: any) => !only || r.status === only);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="row">
        <button className="btn sm" onClick={() => setDay(shiftDay(day, -1))}>←</button>
        <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        <button className="btn sm" onClick={() => setDay(shiftDay(day, 1))}>→</button>
        <BranchSelect value={branch} onChange={setBranch} />
      </div>
      <Err e={error} />
      {s && <>
        <div className="grid tiles">
          <Tile label="Scheduled" value={s.scheduled} sub={`${s.off} day off`} />
          <Tile label="Came" value={s.came} sub={`${s.on_shift} still on shift`} />
          <Tile label="Late" value={s.late} />
          <Tile label="Not marked" value={s.unmarked} sub="≠ absent" />
          <Tile label="Absent (lead)" value={s.absent} />
          <Tile label="Review / conflict" value={s.needs_review + s.conflict} />
        </div>
        <div className="note">{t("notMarkedNote")} — the team lead confirms, HR resolves conflicts.</div>
        <div className="card">
          <div className="row" style={{ marginBottom: 10 }}>
            <h2 style={{ margin: 0 }}>People</h2><span className="spacer" />
            <select value={only} onChange={(e) => setOnly(e.target.value)}>
              <option value="">All statuses</option>
              {["present", "late", "on_shift", "unmarked", "absent", "leave", "needs_review", "conflict", "off"].map((x) => <option key={x}>{x}</option>)}
            </select>
          </div>
          <div className="table-wrap"><table>
            <thead><tr><th>Name</th><th>Branch</th><th>Status</th><th>In</th><th>Out</th><th className="num">Hours</th><th className="num">Late</th><th>Source</th></tr></thead>
            <tbody>{rows.map((r: any) => (
              <tr key={r.employee_id}>
                <td><b>{r.full_name}</b><div className="muted small">{r.position}</div></td><td>{r.branch}</td>
                <td><Status s={r.status} />{r.note && <div className="muted small">{r.note}</div>}</td>
                <td className="mono small">{r.check_in?.slice(11) || "—"}</td><td className="mono small">{r.check_out?.slice(5) || "—"}</td>
                <td className="num">{dash(r.worked_hours)}</td><td className="num">{r.late_min ? `${r.late_min}m` : ""}</td><td className="small">{dash(r.source)}</td>
              </tr>
            ))}</tbody>
          </table></div>
          {rows.length === 0 && <Empty />}
        </div>
      </>}
    </div>
  );
}

export function Tabel() {
  const { me } = usePanel();
  const t = useT();
  const [month, setMonth] = useState(monthISO());
  const [branch, setBranch] = useState("");
  const { data: tb, error, reload } = useLoad<any>(`/api/tabel?month=${month}${branch ? `&branch_id=${branch}` : ""}`, []);
  const [edit, setEdit] = useState<{ emp: any; d: number } | null>(null);
  const [closing, setClosing] = useState<"close" | "reopen" | null>(null);
  const [inT, setInT] = useState("09:00");
  const [outT, setOutT] = useState("18:00");
  const [outNext, setOutNext] = useState(false);
  const write = can(me, "attendance.write");
  const pad = (n: number) => String(n).padStart(2, "0");
  const future = (d: number) => `${month}-${pad(d)}` > todayISO();

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="row">
        <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
        <BranchSelect value={branch} onChange={setBranch} />
        <span className="spacer" />
        {tb && <span className={`badge ${tb.closed ? "b-bad" : "b-ok"}`}>{tb.closed ? "closed" : "open"}</span>}
        <button className="btn" onClick={() => download(`/api/tabel/excel?month=${month}${branch ? `&branch_id=${branch}` : ""}`, `tabel-${month}.xlsx`)}>⤓ {t("download")}</button>
        {write && me.branch_scope === null && tb && (tb.closed
          ? <button className="btn" onClick={() => setClosing("reopen")}>Reopen month</button>
          : <button className="btn primary" onClick={() => setClosing("close")}>Close month</button>)}
      </div>
      <div className="row small muted">
        {[["present", "+ came"], ["late", "L late"], ["on_shift", "~ on shift"], ["absent", "A absent"], ["leave", "V leave"], ["unmarked", "? not marked"], ["needs_review", "R review"], ["conflict", "! conflict"], ["off", "· off"]]
          .map(([k, l]) => <span key={k} className={`cell c-${k}`} style={{ padding: "2px 6px" }}>{l}</span>)}
      </div>
      <Err e={error} />
      {tb && (
        <div className="card">
          <div className="table-wrap"><table className="tabel">
            <thead><tr><th className="name">Employee</th>{tb.days.map((d: number) => <th key={d}>{d}</th>)}<th>Hours</th><th>Norm</th><th>Days</th><th>Late</th><th>Rev.</th><th>?</th></tr></thead>
            <tbody>{tb.rows.map((r: any) => (
              <tr key={r.employee_id}>
                <td className="name"><b>{r.full_name}</b><div className="muted small">{r.branch}</div></td>
                {r.cells.map((c: any) => future(c.d) ? <td key={c.d} /> : (
                  <td key={c.d}><div className={`cell c-${c.s}`} title={`${c.s}${c.src ? " · " + c.src : ""}${c.l ? ` · late ${c.l}m` : ""}`}
                    onClick={() => write && !tb.closed && c.s !== "not_employed" && setEdit({ emp: r, d: c.d })}>{c.h ? Math.round(c.h * 10) / 10 : c.c}</div></td>
                ))}
                <td><b>{r.worked_hours}</b></td><td>{r.norm_hours}</td><td>{r.worked_days}</td><td>{r.late_days}</td><td>{r.review_days}</td><td>{r.unknown_days}</td>
              </tr>
            ))}</tbody>
          </table></div>
          {tb.rows.length === 0 && <Empty />}
        </div>
      )}
      {edit && (
        <ReasonModal title={`${edit.emp.full_name} · ${month}-${pad(edit.d)}`} onClose={() => setEdit(null)}
          extra={<div className="stack">
            <p className="muted small" style={{ margin: 0 }}>HR edit has top priority over the lead report and self check-in. It is written to the audit log.</p>
            <div className="row">
              <label className="field">Check-in<input type="time" value={inT} onChange={(e) => setInT(e.target.value)} /></label>
              <label className="field">Check-out<input type="time" value={outT} onChange={(e) => setOutT(e.target.value)} /></label>
            </div>
            <label className="row small"><input type="checkbox" checked={outNext} onChange={(e) => setOutNext(e.target.checked)} /> check-out next day (overnight / 24h shift)</label>
          </div>}
          onSubmit={async (reason) => {
            const day = `${month}-${pad(edit.d)}`;
            await api("/api/tabel/override", { body: { employee_id: edit.emp.employee_id, day, reason,
              check_in: inT ? `${day}T${inT}` : null, check_out: outT ? `${outNext ? shiftDay(day, 1) : day}T${outT}` : null } });
            reload();
          }} />
      )}
      {closing && <ReasonModal title={closing === "close" ? "Close timesheet month" : "Reopen timesheet month"} onClose={() => setClosing(null)}
        onSubmit={async (reason) => { await api(`/api/tabel/${month}/${closing}`, { body: { reason } }); reload(); }} />}
    </div>
  );
}
