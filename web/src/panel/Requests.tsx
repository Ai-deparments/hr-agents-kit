import { ArrowRight, CornerDownRight } from "lucide-react";
import { useState } from "react";
import { api, dash } from "../api";
import { tEnum, useT } from "../i18n";
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
          <button key={s} className={`pill ${status === s ? "active" : ""}`} onClick={() => setStatus(s)}>{s ? tEnum(t, "st_", s) : t("all")}</button>))}</div>
        <span className="spacer" /><span className="muted small">{t("rq_autoNote")}</span>
      </div>
      <Err e={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>{t("c_employee")}</th><th>{t("c_kind")}</th><th>{t("rq_dates")}</th><th className="num">{t("c_days")}</th><th>{t("c_comment")}</th><th>{t("rq_channel")}</th><th>{t("c_status")}</th><th /></tr></thead>
        <tbody>{data?.map((r) => (
          <tr key={r.id}>
            <td><b>{r.full_name}</b><div className="muted small">{r.branch}</div></td><td>{r.kind}</td>
            <td className="mono small">{dash(r.date_from)} <ArrowRight className="ic inl" size={14} aria-hidden="true" /> {dash(r.date_to)}</td><td className="num">{dash(r.days)}</td>
            <td className="small">{r.comment}{r.decision_reason && <div className="muted"><CornerDownRight className="ic inl" size={14} aria-hidden="true" /> {r.decision_reason} ({r.decided_by})</div>}</td>
            <td className="small">{r.channel}</td><td><Status s={r.status} /></td>
            <td>{r.status === "pending" && can(me, "requests.decide") && <div className="row">
              <button className="btn sm primary" onClick={() => setDecide({ id: r.id, approve: true })}>{t("approve")}</button>
              <button className="btn sm danger" onClick={() => setDecide({ id: r.id, approve: false })}>{t("reject")}</button></div>}</td>
          </tr>
        ))}</tbody>
      </table></div>
      {data?.length === 0 && <Empty />}
      {decide && <ReasonModal title={decide.approve ? t("rq_approveReq") : t("rq_rejectReq")} confirmLabel={decide.approve ? t("approve") : t("reject")}
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
      <div className="note">{t("rq_humanOnly")}</div>
      <div className="card">
        <div className="pills" style={{ marginBottom: 12 }}>{["pending", "approved", "rejected"].map((s) => (
          <button key={s} className={`pill ${status === s ? "active" : ""}`} onClick={() => setStatus(s)}>{tEnum(t, "st_", s)}</button>))}</div>
        <Err e={error} />
        <div className="table-wrap"><table>
          <thead><tr><th>{t("c_action")}</th><th>{t("rq_summary")}</th><th>{t("rq_requestedBy")}</th><th>{t("c_when")}</th><th>{t("c_status")}</th><th /></tr></thead>
          <tbody>{data?.map((a) => (
            <tr key={a.id}>
              <td><span className="badge b-info">{a.action}</span></td><td>{a.summary}{a.decision_reason && <div className="muted small"><CornerDownRight className="ic inl" size={14} aria-hidden="true" /> {a.decision_reason}</div>}</td>
              <td className="small">{a.requested_by}</td><td className="mono small">{String(a.created_at).slice(0, 16).replace("T", " ")}</td><td><Status s={a.status} /></td>
              <td>{a.status === "pending" && can(me, "hr.write") && <div className="row">
                <button className="btn sm primary" onClick={() => setDecide({ id: a.id, approve: true })}>{t("approve")}</button>
                <button className="btn sm danger" onClick={() => setDecide({ id: a.id, approve: false })}>{t("reject")}</button></div>}</td>
            </tr>
          ))}</tbody>
        </table></div>
        {data?.length === 0 && <Empty text={t("rq_noAgentReq")} />}
      </div>
      {decide && <ReasonModal title={decide.approve ? t("rq_approveAction") : t("rq_rejectAction")} onClose={() => setDecide(null)}
        onSubmit={async (reason) => { await api(`/api/approvals/${decide.id}/decide`, { body: { approve: decide.approve, reason } }); reload(); }} />}
    </div>
  );
}
