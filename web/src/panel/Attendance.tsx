import { useState } from "react";
import { api, dash, download, monthISO, shiftDay, todayISO } from "../api";
import { tEnum, useT } from "../i18n";
import { Empty, Err, ReasonModal, Status, Tile, useLoad } from "../ui";
import { can, usePanel } from "./ctx";
import { LatenessRule, Nudges } from "./Nudges";

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
  const { me } = usePanel();
  return (
    <div className="stack" style={{ gap: 14 }}>
      {can(me, "broadcast") && <Nudges />}
      {can(me, "attendance.write") && <LatenessRule />}
      <div className="row">
        <button className="btn sm" onClick={() => setDay(shiftDay(day, -1))}>←</button>
        <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        <button className="btn sm" onClick={() => setDay(shiftDay(day, 1))}>→</button>
        <BranchSelect value={branch} onChange={setBranch} />
      </div>
      <Err e={error} />
      {s && <>
        <div className="grid tiles">
          <Tile label={t("at_scheduled")} value={s.scheduled} sub={`${s.off} ${t("at_dayOff")}`} />
          <Tile label={t("came")} value={s.came} sub={`${s.on_shift} ${t("at_stillOn")}`} />
          <Tile label={t("c_late")} value={s.late} />
          <Tile label={t("at_notMarked")} value={s.unmarked} sub={t("at_neAbsent")} />
          <Tile label={t("at_absentLead")} value={s.absent} />
          <Tile label={t("at_reviewConflict")} value={s.needs_review + s.conflict} />
        </div>
        <div className="note">{t("notMarkedNote")} — {t("at_leadConfirms")}</div>
        <div className="card">
          <div className="row" style={{ marginBottom: 10 }}>
            <h2 style={{ margin: 0 }}>{t("at_people")}</h2><span className="spacer" />
            <select value={only} onChange={(e) => setOnly(e.target.value)}>
              <option value="">{t("at_allStatuses")}</option>
              {["present", "late", "on_shift", "unmarked", "absent", "leave", "needs_review", "conflict", "off"].map((x) => <option key={x} value={x}>{tEnum(t, "st_", x)}</option>)}
            </select>
          </div>
          <div className="table-wrap"><table>
            <thead><tr><th>{t("c_name")}</th><th>{t("c_branch")}</th><th>{t("c_status")}</th><th>{t("at_in")}</th><th>{t("at_out")}</th><th className="num">{t("c_hours")}</th><th className="num">{t("c_late")}</th><th>{t("c_source")}</th></tr></thead>
            <tbody>{rows.map((r: any) => (
              <tr key={r.employee_id}>
                <td><b>{r.full_name}</b><div className="muted small">{r.position}</div></td><td>{r.branch}</td>
                <td><Status s={r.status} />{r.note && <div className="muted small">{r.note}</div>}</td>
                <td className="mono small">{r.check_in?.slice(11) || "—"}</td><td className="mono small">{r.check_out?.slice(5) || "—"}</td>
                <td className="num">{dash(r.worked_hours)}</td><td className="num">{r.late_min ? `${r.late_min}${t("c_mUnit")}` : ""}</td><td className="small">{dash(r.source)}</td>
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
        {tb && <span className={`badge ${tb.closed ? "b-bad" : "b-ok"}`}>{tb.closed ? t("st_closed") : t("st_open")}</span>}
        <button className="btn" onClick={() => download(`/api/tabel/excel?month=${month}${branch ? `&branch_id=${branch}` : ""}`, `tabel-${month}.xlsx`)}>⤓ {t("download")}</button>
        {write && me.branch_scope === null && tb && (tb.closed
          ? <button className="btn" onClick={() => setClosing("reopen")}>{t("at_reopen")}</button>
          : <button className="btn primary" onClick={() => setClosing("close")}>{t("at_closeMonth")}</button>)}
      </div>
      <div className="row small muted">
        {[["present", "+"], ["late", "L"], ["on_shift", "~"], ["absent", "A"], ["leave", "V"], ["unmarked", "?"], ["needs_review", "R"], ["conflict", "!"], ["off", "·"]]
          .map(([k, l]) => <span key={k} className={`cell c-${k}`} style={{ padding: "2px 6px" }}>{l} {t("st_" + k)}</span>)}
      </div>
      <Err e={error} />
      {tb && (
        <div className="card">
          <div className="table-wrap"><table className="tabel">
            <thead><tr><th className="name">{t("c_employee")}</th>{tb.days.map((d: number) => <th key={d}>{d}</th>)}<th>{t("c_hours")}</th><th>{t("at_norm")}</th><th>{t("c_days")}</th><th>{t("c_late")}</th><th>{t("at_rev")}</th><th>?</th></tr></thead>
            <tbody>{tb.rows.map((r: any) => (
              <tr key={r.employee_id}>
                <td className="name"><b>{r.full_name}</b><div className="muted small">{r.branch}</div></td>
                {r.cells.map((c: any) => future(c.d) ? <td key={c.d} /> : (
                  <td key={c.d}><div className={`cell c-${c.s}`} title={`${tEnum(t, "st_", c.s)}${c.src ? " · " + c.src : ""}${c.l ? ` · ${t("st_late")} ${c.l}${t("c_mUnit")}` : ""}`}
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
            <p className="muted small" style={{ margin: 0 }}>{t("at_hrEditNote")}</p>
            <div className="row">
              <label className="field">{t("at_checkIn")}<input type="time" value={inT} onChange={(e) => setInT(e.target.value)} /></label>
              <label className="field">{t("at_checkOut")}<input type="time" value={outT} onChange={(e) => setOutT(e.target.value)} /></label>
            </div>
            <label className="row small"><input type="checkbox" checked={outNext} onChange={(e) => setOutNext(e.target.checked)} /> {t("at_outNext")}</label>
          </div>}
          onSubmit={async (reason) => {
            const day = `${month}-${pad(edit.d)}`;
            await api("/api/tabel/override", { body: { employee_id: edit.emp.employee_id, day, reason,
              check_in: inT ? `${day}T${inT}` : null, check_out: outT ? `${outNext ? shiftDay(day, 1) : day}T${outT}` : null } });
            reload();
          }} />
      )}
      {closing && <ReasonModal title={closing === "close" ? t("at_closeTitle") : t("at_reopenTitle")} onClose={() => setClosing(null)}
        onSubmit={async (reason) => { await api(`/api/tabel/${month}/${closing}`, { body: { reason } }); reload(); }} />}
    </div>
  );
}
