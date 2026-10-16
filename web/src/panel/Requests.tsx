import { useState } from "react";
import { api, dash } from "../api";
import { useT } from "../i18n";
import { Empty, Err, ReasonModal, Status, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

export function Requests() {
  const { me } = usePanel();
  const t = useT();
  const [status, setStatus] = useState("pending");
  const { data, error, reload } = useLoad<any[]>(`/api/requests${status ? `?status=${status}` : ""}`, []);
  const [decide, setDecide] = useState<{ id: number; approve: boolean } | null>(null);
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <div className="pills">{["pending", "approved", "rejected", ""].map((s) => (
          <button key={s} className={`pill ${status === s ? "active" : ""}`} onClick={() => setStatus(s)}>{s || "all"}</button>))}</div>
        <span className="spacer" /><span className="muted small">Approved vacation / sick leave goes to the timesheet automatically.</span>
      </div>
      <Err e={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>Employee</th><th>Kind</th><th>Dates</th><th className="num">Days</th><th>Comment</th><th>Channel</th><th>Status</th><th /></tr></thead>
        <tbody>{data?.map((r) => (
          <tr key={r.id}>
            <td><b>{r.full_name}</b><div className="muted small">{r.branch}</div></td><td>{r.kind}</td>
            <td className="mono small">{dash(r.date_from)} → {dash(r.date_to)}</td><td className="num">{dash(r.days)}</td>
            <td className="small">{r.comment}{r.decision_reason && <div className="muted">→ {r.decision_reason} ({r.decided_by})</div>}</td>
            <td className="small">{r.channel}</td><td><Status s={r.status} /></td>
            <td>{r.status === "pending" && can(me, "requests.decide") && <div className="row">
              <button className="btn sm primary" onClick={() => setDecide({ id: r.id, approve: true })}>{t("approve")}</button>
              <button className="btn sm danger" onClick={() => setDecide({ id: r.id, approve: false })}>{t("reject")}</button></div>}</td>
          </tr>
        ))}</tbody>
      </table></div>
      {data?.length === 0 && <Empty />}
      {decide && <ReasonModal title={decide.approve ? "Approve request" : "Reject request"} confirmLabel={decide.approve ? t("approve") : t("reject")}
        onClose={() => setDecide(null)} onSubmit={async (reason) => { await api(`/api/requests/${decide.id}/decide`, { body: { approve: decide.approve, reason } }); reload(); }} />}
    </div>
  );
}

export function Approvals() {
  const { me } = usePanel();
  const t = useT();
  const [status, setStatus] = useState("pending");
  const { data, error, reload } = useLoad<any[]>(`/api/approvals?status=${status}`, []);
  const [decide, setDecide] = useState<{ id: number; approve: boolean } | null>(null);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="note">Seven decisions are human-only: payroll approval, deductions, contract changes, hiring, firing, mass broadcasts, request approval. Agents can only ask — you decide here.</div>
      <div className="card">
        <div className="pills" style={{ marginBottom: 12 }}>{["pending", "approved", "rejected"].map((s) => (
          <button key={s} className={`pill ${status === s ? "active" : ""}`} onClick={() => setStatus(s)}>{s}</button>))}</div>
        <Err e={error} />
        <div className="table-wrap"><table>
          <thead><tr><th>Action</th><th>Summary</th><th>Requested by</th><th>When</th><th>Status</th><th /></tr></thead>
          <tbody>{data?.map((a) => (
            <tr key={a.id}>
              <td><span className="badge b-info">{a.action}</span></td><td>{a.summary}{a.decision_reason && <div className="muted small">→ {a.decision_reason}</div>}</td>
              <td className="small">{a.requested_by}</td><td className="mono small">{String(a.created_at).slice(0, 16).replace("T", " ")}</td><td><Status s={a.status} /></td>
              <td>{a.status === "pending" && can(me, "hr.write") && <div className="row">
                <button className="btn sm primary" onClick={() => setDecide({ id: a.id, approve: true })}>{t("approve")}</button>
                <button className="btn sm danger" onClick={() => setDecide({ id: a.id, approve: false })}>{t("reject")}</button></div>}</td>
            </tr>
          ))}</tbody>
        </table></div>
        {data?.length === 0 && <Empty text="No requests from agents" />}
      </div>
      {decide && <ReasonModal title={decide.approve ? "Approve action" : "Reject action"} onClose={() => setDecide(null)}
        onSubmit={async (reason) => { await api(`/api/approvals/${decide.id}/decide`, { body: { approve: decide.approve, reason } }); reload(); }} />}
    </div>
  );
}
