import { money } from "../api";
import { Empty, Err, Light, Tile, useLoad } from "../ui";

export default function Dashboard() {
  const { data: d, error } = useLoad<any>("/api/dashboard");
  if (error) return <Err e={error} />;
  if (!d) return <div className="muted">Loading…</div>;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="grid tiles">
        <Tile label="Active staff" value={d.active} />
        {d.fund !== null && <Tile label="Salary fund" value={money(d.fund)} sub="base salaries, UZS" />}
        <Tile label="On shift today" value={`${d.on_shift_today} / ${d.scheduled_today}`} sub={`${d.unmarked_today} not marked · source: ${d.attendance_source}`} />
        <Tile label="Late today" value={d.late_today} />
        <Tile label="Pending requests" value={d.pending_requests} />
        <Tile label="Agent approvals" value={d.pending_approvals} sub="human-only decisions" />
        <Tile label="New candidates" value={d.new_candidates} />
        <Tile label="Docs expiring 30d" value={d.documents_30d} />
      </div>
      <div className="note">Not marked ≠ absent. Unknown values are shown as “—”, never as 0.</div>
      <div className="grid two">
        <div className="card">
          <h2>Branches</h2>
          <div className="table-wrap"><table>
            <thead><tr><th>Branch</th><th className="num">People</th>{d.fund !== null && <><th className="num">Fund</th><th className="num">Avg</th></>}</tr></thead>
            <tbody>{d.branches.map((b: any) => (
              <tr key={b.branch}><td>{b.branch}</td><td className="num">{b.people}</td>
                {d.fund !== null && <><td className="num">{money(b.fund)}</td><td className="num">{money(b.avg_salary)}</td></>}</tr>
            ))}</tbody>
          </table></div>
        </div>
        <div className="stack">
          <div className="card">
            <h2>Onboarding (30/60/90)</h2>
            <div className="grid tiles" style={{ gridTemplateColumns: "repeat(2, 1fr)" }}>
              <div><div className="muted small">In plan</div><div className="num" style={{ fontSize: 20, fontWeight: 700 }}>{d.onboarding.total}</div></div>
              <div><div className="muted small">Behind</div><div className="num" style={{ fontSize: 20, fontWeight: 700, color: "var(--bad)" }}>{d.onboarding.behind}</div></div>
              <div><div className="muted small">No mentor</div><div className="num" style={{ fontSize: 20, fontWeight: 700 }}>{d.onboarding.no_mentor}</div></div>
              <div><div className="muted small">No test yet</div><div className="num" style={{ fontSize: 20, fontWeight: 700 }}>{d.onboarding.no_test}</div></div>
            </div>
          </div>
          <div className="card">
            <h2>Open vacancies</h2>
            {d.vacancies.length === 0 ? <Empty /> : d.vacancies.map((v: any) => (
              <div key={v.id} className="row" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
                <Light c={v.light} /><b>{v.title}</b><span className="muted small">{v.branch}</span><span className="spacer" />
                <span className="num small">{v.days_open}/{v.sla_days} d · {v.candidates} cand.</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
