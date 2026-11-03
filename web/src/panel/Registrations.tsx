import { useContext, useState } from "react";
import { api, dash } from "../api";
import { LangCtx, useT } from "../i18n";
import { Empty, Err, Modal, ReasonModal, Status, useLoad } from "../ui";
import { usePanel } from "./ctx";
import { ago } from "./Users";

export type CatalogItem = { code: string; uz: string; ru: string };
export type Catalog = { permissions: CatalogItem[]; bot_functions: CatalogItem[] };
type Reg = { id: number; telegram_id: number; tg_username: string | null; full_name: string; position_text: string;
  region_text: string; status: string; functions: string[]; decided_by: string | null; decision_reason: string | null;
  created_at: string; employee_id: number | null; source: string; bots: string[]; last_at: string; requests: number };

export function useDesc() {
  const { lang } = useContext(LangCtx);
  return (i: CatalogItem) => (lang === "uz" ? i.uz : i.ru);
}

export function Checks({ items, value, onChange }: { items: CatalogItem[]; value: string[]; onChange: (v: string[]) => void }) {
  const d = useDesc();
  return (
    <div className="checks">
      {items.map((i) => (
        <label key={i.code} className="check">
          <input type="checkbox" checked={value.includes(i.code)}
            onChange={(e) => onChange(e.target.checked ? [...value, i.code] : value.filter((x) => x !== i.code))} />
          <span><b>{d(i)}</b><span>{i.code}</span></span>
        </label>
      ))}
    </div>
  );
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-zа-яё0-9]/gi, "");

function Approve({ reg, catalog, onClose, onDone }: { reg: Reg; catalog: Catalog; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const { dicts } = usePanel();
  const guessPos = dicts.positions.find((p) => norm(p.title) === norm(reg.position_text))?.id;
  const guessRegion = dicts.regions.find((r) => norm(r.name).includes(norm(reg.region_text)) || norm(reg.region_text).includes(norm(r.name)))?.id;
  const [mode, setMode] = useState<"new" | "link">("new");
  const [employeeId, setEmployeeId] = useState<number | "">("");
  const [branchId, setBranchId] = useState<number | "">(dicts.branches.find((b) => b.region_id === guessRegion)?.id ?? "");
  const [deptId, setDeptId] = useState<number | "">("");
  const [posId, setPosId] = useState<number | "">(guessPos ?? "");
  const [fns, setFns] = useState<string[]>(["helpdesk"]);
  const [q, setQ] = useState(reg.full_name.split(" ")[0]);
  const emps = useLoad<{ id: number; full_name: string; branch: string | null; telegram_linked: boolean }[]>(
    mode === "link" ? `/api/employees?q=${encodeURIComponent(q)}` : null, [q, mode]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await api(`/api/registrations/${reg.id}/approve`, { body: {
        functions: fns, employee_id: mode === "link" ? employeeId || null : null,
        branch_id: branchId || null, department_id: deptId || null, position_id: posId || null } });
      onDone(); onClose();
    } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };

  return (
    <Modal title={`${t("approve")}: ${reg.full_name}`} onClose={onClose}>
      <div className="stack">
        <div className="note">{reg.position_text} · {reg.region_text} · tg {reg.tg_username ? `@${reg.tg_username}` : reg.telegram_id}</div>
        <label className="field">{t.l("Xodim kartasi", "Карточка сотрудника", "Employee card")}
          <select value={mode} onChange={(e) => setMode(e.target.value as "new" | "link")}>
            <option value="new">{t.l("Yangi karta ochish", "Создать новую", "Create new")}</option>
            <option value="link">{t.l("Mavjud xodimga bog'lash", "Привязать к существующему", "Link to existing")}</option>
          </select>
        </label>
        {mode === "link" ? (
          <>
            <input placeholder={t("search")} value={q} onChange={(e) => setQ(e.target.value)} />
            <select value={employeeId} onChange={(e) => setEmployeeId(Number(e.target.value) || "")}>
              <option value="">—</option>
              {(emps.data || []).map((e) => <option key={e.id} value={e.id} disabled={e.telegram_linked}>
                {e.full_name} · {dash(e.branch)}{e.telegram_linked ? " · TG" : ""}</option>)}
            </select>
          </>
        ) : (
          <label className="field">{t("branches")}
            <select value={branchId} onChange={(e) => setBranchId(Number(e.target.value) || "")} required>
              <option value="">—</option>
              {dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
        )}
        <div className="grid two">
          <label className="field">{t("departments")}
            <select value={deptId} onChange={(e) => setDeptId(Number(e.target.value) || "")}>
              <option value="">—</option>
              {dicts.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </label>
          <label className="field">{t("positions")}
            <select value={posId} onChange={(e) => setPosId(Number(e.target.value) || "")}>
              <option value="">—</option>
              {dicts.positions.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}
            </select>
          </label>
        </div>
        <h2 style={{ margin: "4px 0 0" }}>{t("functions")}</h2>
        <Checks items={catalog.bot_functions} value={fns} onChange={setFns} />
        <Err e={err} />
        <div className="row"><span className="spacer" />
          <button className="btn" onClick={onClose}>{t("cancel")}</button>
          <button className="btn primary" disabled={busy || (mode === "new" ? !branchId : !employeeId)} onClick={submit}>{t("approve")}</button>
        </div>
      </div>
    </Modal>
  );
}

export default function Registrations() {
  const t = useT();
  const d = useDesc();
  const [status, setStatus] = useState("pending");
  const list = useLoad<Reg[]>(`/api/registrations?status=${status}`, [status]);
  const catalog = useLoad<Catalog>("/api/org/catalog");
  const [approve, setApprove] = useState<Reg | null>(null);
  const [reject, setReject] = useState<Reg | null>(null);
  const [rejectAll, setRejectAll] = useState(false);
  const fnName = (c: string) => { const i = catalog.data?.bot_functions.find((x) => x.code === c); return i ? d(i) : c; };
  const dt = (v: string) => new Date(v).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
  const pendingAccess = (list.data || []).filter((r) => r.status === "pending" && r.source === "access").length;

  return (
    <div className="stack">
      <p className="muted page-intro">{t.l("Agentlarga yozgan notanish odamlar. Bot ularga javob bermaydi — kim nimani ko'rishini siz hal qilasiz.",
        "Незнакомые люди, написавшие агентам. Бот им не отвечает — кто что видит, решаете вы.", "")}</p>
      <div className="toolbar">
        <select className="ctl" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="pending">{t.l("Kutmoqda", "Ожидают", "Pending")}</option>
          <option value="approved">{t.l("Tasdiqlangan", "Подтверждённые", "Approved")}</option>
          <option value="rejected">{t.l("Rad etilgan", "Отклонённые", "Rejected")}</option>
          <option value="">{t("all")}</option>
        </select>
        <span className="spacer" />
        {status === "pending" && pendingAccess > 0 && <button className="btn danger" onClick={() => setRejectAll(true)}>
          {t.l("Hammasini rad etish", "Отклонить всех", "Reject all")}</button>}
      </div>
      <div className="callout">{t.l("Ism va username Telegram'dan keladi — ularni odamning o'zi yozgan. Tasdiqlashdan oldin shaxsini tekshiring.",
        "Имя и username приходят из Telegram — их пишет сам человек. Перед подтверждением проверьте личность.", "")}</div>
      <Err e={list.error} />
      <div className="card">
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>{t.l("Ism", "Имя", "Name")}</th><th>@username</th><th className="ph-hide">Telegram ID</th><th className="ph-hide">{t.l("Botlar", "Боты", "Bots")}</th>
              <th>{t.l("Birinchi / oxirgi", "Первый / последний", "First / last")}</th><th className="r">{t.l("So'rovlar soni", "Обращений", "Requests")}</th><th className="r">{t.l("Amallar", "Действия", "Actions")}</th></tr></thead>
            <tbody>
              {(list.data || []).map((r) => (
                <tr key={r.id}>
                  <td><b style={{ fontWeight: 600 }}>{r.full_name}</b>
                    {r.source === "form" && <span className="sub">{[r.position_text, r.region_text].filter(Boolean).join(" · ")}</span>}
                    {r.functions.length > 0 && <span className="sub">{r.functions.map(fnName).join(", ")}</span>}
                    {r.decision_reason && <span className="sub">{r.decision_reason}</span>}</td>
                  <td>{r.tg_username ? `@${r.tg_username}` : "—"}</td>
                  <td className="small ph-hide">{r.telegram_id}</td>
                  <td className="ph-hide">{(r.bots.length ? r.bots : ["bot"]).map((b) => <span key={b} className="badge" style={{ marginRight: 4 }}>{b}</span>)}</td>
                  <td className="small">{dt(r.created_at)}<span className="sub">{ago(t, r.last_at)}</span></td>
                  <td className="r">{r.requests} {t.l("marta", "раз", "×")}</td>
                  <td className="r">{r.status === "pending" ? <div className="row" style={{ justifyContent: "flex-end" }}>
                    <button className="btn sm" onClick={() => setReject(r)}>{t.l("Rad etish", "Отклонить", "Reject")}</button>
                    <button className="btn sm primary" disabled={!catalog.data} onClick={() => setApprove(r)}>{t.l("Tasdiqlash", "Подтвердить", "Approve")}</button>
                  </div> : <Status s={r.status} />}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {list.data?.length === 0 && <Empty />}
        </div>
      </div>
      {approve && catalog.data && <Approve reg={approve} catalog={catalog.data} onClose={() => setApprove(null)} onDone={list.reload} />}
      {reject && <ReasonModal title={`${t.l("Rad etish", "Отклонить", "Reject")}: ${reject.full_name}`} onClose={() => setReject(null)}
        onSubmit={(reason) => api(`/api/registrations/${reject.id}/reject`, { body: { reason } }).then(list.reload)} />}
      {rejectAll && <ReasonModal title={t.l("Hammasini rad etish", "Отклонить всех", "Reject all")} onClose={() => setRejectAll(false)}
        onSubmit={(reason) => api("/api/registrations/reject-all", { body: { reason } }).then(list.reload)} />}
    </div>
  );
}
