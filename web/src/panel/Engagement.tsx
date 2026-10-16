import { useState } from "react";
import { api, dash } from "../api";
import { Empty, Err, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

/** SOP read coverage, anonymous eNPS / exit survey, turnover-risk signals (HR only), check-in geofences. */
export default function Engagement() {
  const { me, dicts } = usePanel();
  const sops = useLoad<any[]>("/api/engagement/sops");
  const pulse = useLoad<any>("/api/engagement/pulse?months=6");
  const hr = can(me, "hr.write");
  const risk = useLoad<any>(hr ? "/api/engagement/risk" : null);
  const branchName = (id: string) => dicts.branches.find((b) => String(b.id) === id)?.name || "—";
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="grid two">
        <div className="card">
          <h2>eNPS (anonymous)</h2>
          <Err e={pulse.error} />
          <div className="muted small" style={{ marginBottom: 8 }}>Answers are stored without names. Groups with fewer than {pulse.data?.min_group ?? 5} answers are hidden.</div>
          {pulse.data && Object.keys(pulse.data.enps_by_month).length === 0 && <Empty text="No answers yet — the bot asks once a month." />}
          {pulse.data && Object.entries(pulse.data.enps_by_month).map(([m, v]: any) => (
            <div key={m} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
              <b>{m}</b><span className="muted small">{v.answers} answers</span><span className="spacer" />
              <b className="num" style={{ color: v.enps === null ? "var(--ink-2)" : v.enps >= 20 ? "var(--ok)" : v.enps < 0 ? "var(--bad)" : "var(--warn)" }}>{v.enps === null ? "hidden (<5)" : `${v.enps > 0 ? "+" : ""}${v.enps}`}</b>
            </div>
          ))}
          {pulse.data && Object.keys(pulse.data.enps_by_branch).length > 0 && <>
            <h2 style={{ marginTop: 14 }}>By branch</h2>
            {Object.entries(pulse.data.enps_by_branch).map(([b, v]: any) => (
              <div key={b} className="row small" style={{ padding: "3px 0" }}><span>{branchName(b)}</span><span className="spacer" />
                <span className="muted">{v.answers}</span><b className="num">{v.enps === null ? "—" : v.enps}</b></div>
            ))}
          </>}
          <h2 style={{ marginTop: 14 }}>Exit survey</h2>
          {pulse.data?.exit_reasons ? Object.entries(pulse.data.exit_reasons).map(([r, n]: any) => (
            <div key={r} className="row small"><span>{r}</span><span className="spacer" /><b className="num">{n}</b></div>
          )) : <div className="muted small">{pulse.data?.exit_answers ?? 0} answers — reasons appear from 5.</div>}
        </div>
        <div className="card">
          <h2>Rules read (current version)</h2>
          <Err e={sops.error} />
          <div className="table-wrap"><table>
            <thead><tr><th>SOP</th><th>For</th><th className="num">Read</th><th className="num">%</th></tr></thead>
            <tbody>{sops.data?.map((s) => (
              <tr key={s.id}><td>{s.title}</td><td className="small">{s.position}</td><td className="num">{s.read}/{s.target}</td>
                <td className="num"><b style={{ color: s.pct === null ? undefined : s.pct >= 90 ? "var(--ok)" : s.pct < 50 ? "var(--bad)" : "var(--warn)" }}>{dash(s.pct)}</b></td></tr>
            ))}</tbody>
          </table></div>
          {sops.data?.length === 0 && <Empty />}
          <div className="muted small" style={{ marginTop: 8 }}>Employees confirm “read” in Suhayl; an edited SOP needs a new confirmation. Monday reminders go to those who have not read it.</div>
        </div>
      </div>
      {hr && <div className="card">
        <h2>Turnover-risk signals</h2>
        <div className="note" style={{ marginBottom: 10 }}>{risk.data?.note || "Explainable rules, not a prediction. Use them to start a conversation — never as a decision."}</div>
        <Err e={risk.error} />
        {risk.data?.rows.length === 0 && <Empty text="No signals right now" />}
        {risk.data?.rows.map((r: any) => (
          <div key={r.employee_id} className="row" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)", alignItems: "flex-start" }}>
            <span className={`badge ${r.level === "high" ? "b-bad" : "b-warn"}`}>{r.level}</span>
            <div><b>{r.full_name}</b> <span className="muted small">{r.branch}</span>
              <div className="small">{r.signals.join(" · ")}</div></div>
          </div>
        ))}
      </div>}
      {hr && me.branch_scope === null && <GeoZones />}
    </div>
  );
}

function GeoZones() {
  const { dicts } = usePanel();
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState<Record<number, any>>({});
  const save = async (id: number) => {
    const f = form[id] || {};
    try {
      await api(`/api/engagement/branches/${id}/geo`, { method: "PATCH", body: {
        lat: f.lat === "" || f.lat === undefined ? null : Number(f.lat), lon: f.lon === "" || f.lon === undefined ? null : Number(f.lon),
        radius_m: f.radius_m ? Number(f.radius_m) : null } });
      setMsg("Saved");
    } catch (x: any) { setMsg(x.message); }
  };
  const set = (id: number, k: string, v: string) => setForm({ ...form, [id]: { ...(form[id] || {}), [k]: v } });
  return (
    <div className="card">
      <h2>Check-in zones</h2>
      <div className="muted small" style={{ marginBottom: 8 }}>Branch centre and radius for the “Keldim” GPS check. Copy coordinates from Google/Yandex Maps. With mode <b>geo_or_qr</b>, people outside the zone can scan the head's rotating QR instead.</div>
      {msg && <div className="note">{msg}</div>}
      <div className="table-wrap"><table>
        <thead><tr><th>Branch</th><th>Latitude</th><th>Longitude</th><th>Radius, m</th><th /></tr></thead>
        <tbody>{dicts.branches.map((b: any) => (
          <tr key={b.id}><td>{b.name}</td>
            <td><input style={{ width: 110 }} placeholder="lat" defaultValue={b.lat ?? ""} onChange={(e) => set(b.id, "lat", e.target.value)} /></td>
            <td><input style={{ width: 110 }} placeholder="lon" defaultValue={b.lon ?? ""} onChange={(e) => set(b.id, "lon", e.target.value)} /></td>
            <td><input style={{ width: 80 }} placeholder="150 m" defaultValue={b.radius_m ?? ""} onChange={(e) => set(b.id, "radius_m", e.target.value)} /></td>
            <td><button className="btn sm primary" onClick={() => save(b.id)}>Save</button></td></tr>
        ))}</tbody>
      </table></div>
    </div>
  );
}
