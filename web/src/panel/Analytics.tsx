import { useState } from "react";
import { Err, Tile, useLoad } from "../ui";

function Bars({ groups }: { groups: Record<string, number> }) {
  const max = Math.max(1, ...Object.values(groups));
  return (
    <div className="stack" style={{ gap: 6 }}>
      {Object.entries(groups).map(([k, v]) => (
        <div key={k} className="row" style={{ flexWrap: "nowrap" }}>
          <span style={{ width: 150, flexShrink: 0 }} className="small">{k}</span>
          <div style={{ flex: 1, background: "var(--muted-bg)", borderRadius: 6, height: 14 }}>
            <div style={{ width: `${(100 * v) / max}%`, background: "var(--primary)", height: "100%", borderRadius: 6 }} />
          </div>
          <span className="num small" style={{ width: 36, textAlign: "right" }}>{v}</span>
        </div>
      ))}
    </div>
  );
}

export default function Analytics() {
  const [months, setMonths] = useState(3);
  const { data: a, error } = useLoad<any>(`/api/analytics?months=${months}`, []);
  if (error) return <Err e={error} />;
  if (!a) return <div className="muted">Loading…</div>;
  const t = a.turnover;
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="row"><span className="muted">Turnover period</span>
        <select value={months} onChange={(e) => setMonths(Number(e.target.value))}>{[1, 3, 6, 12, 24].map((m) => <option key={m} value={m}>{m} months</option>)}</select></div>
      <div className="note">Every number has its base. Groups under 10 people show counts, not percent.</div>
      <div className="grid tiles">
        <Tile label="Headcount" value={a.headcount_branch.total} sub={`${a.headcount_branch.probation} on probation`} />
        <Tile label="Turnover" value={t.left} sub={t.rate} />
        <Tile label="Left in first 30 days" value={t.left_first_30_days} sub={t.period} />
        <Tile label="Attendance 30d" value={a.attendance_30d.rate_pct === null ? "—" : `${a.attendance_30d.rate_pct}%`} sub={a.attendance_30d.base} />
      </div>
      <div className="grid two">
        <div className="card"><h2>Headcount by branch</h2><Bars groups={a.headcount_branch.groups} /></div>
        <div className="card"><h2>Headcount by position</h2><Bars groups={a.headcount_position.groups} /></div>
        {[["Turnover by branch", t], ["Turnover by region", a.turnover_region]].map(([title, tt]: any) => (
          <div key={title} className="card"><h2>{title}</h2>
            <div className="table-wrap"><table><thead><tr><th>Group</th><th className="num">Left</th><th className="num">Base</th><th>Rate</th></tr></thead>
              <tbody>{Object.entries(tt.groups).map(([k, v]: any) => <tr key={k}><td>{k}</td><td className="num">{v.left}</td><td className="num">{v.base}</td><td className="small">{v.rate}</td></tr>)}</tbody></table></div>
          </div>
        ))}
        <div className="card"><h2>Most missed / late (30 days)</h2>
          <div className="table-wrap"><table><thead><tr><th>Name</th><th>Branch</th><th className="num">Missed</th><th className="num">Late</th></tr></thead>
            <tbody>{a.attendance_30d.top.map((r: any) => <tr key={r.full_name}><td>{r.full_name}</td><td>{r.branch}</td><td className="num">{r.missed}</td><td className="num">{r.late}</td></tr>)}</tbody></table></div>
        </div>
      </div>
    </div>
  );
}
