import { useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import { Ic } from "../icons";
import { Empty, Err, Modal, useLoad } from "../ui";
import { usePanel } from "./ctx";
import { Catalog, Checks, useDesc } from "./Registrations";

type User = { id: number; username: string; full_name: string; role: string; branch_scope: number[] | null; can_see_payroll: boolean;
  active: boolean; telegram_id: number | null; last_login: string | null };
type Role = { code: string; name: string; perms: string[] };
type Invite = { id: number; role: string; status: string; tg_name: string | null; tg_username: string | null; telegram_id: number | null;
  created_by: string; created_at: string; used_at: string | null; expires_at: string; link?: string };
type BotUser = { id: number; full_name: string; position: string | null; department: string | null; telegram_id: number;
  functions: string[]; status: string; last_message: string | null };

export function ago(t: ReturnType<typeof useT>, iso: string | null): string {
  if (!iso) return "—";
  const d = (Date.now() - new Date(iso).getTime()) / 86400000;
  if (d < 1) return t.l("bugun", "сегодня", "today");
  if (d < 2) return t.l("kecha", "вчера", "yesterday");
  return t.l(`${Math.floor(d)} kun oldin`, `${Math.floor(d)} дн. назад`, `${Math.floor(d)} d ago`);
}

const initials = (s: string) => s.split(/\s+/).map((x) => x[0]).join("").slice(0, 1).toUpperCase();

function InviteModal({ roles, onClose }: { roles: Role[]; onClose: () => void }) {
  const t = useT();
  const [role, setRole] = useState(roles.find((r) => !r.perms.includes("*"))?.code || roles[0]?.code || "");
  const [pay, setPay] = useState(false);
  const [res, setRes] = useState<Invite | null>(null);
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal title={t.l("Telegram orqali qo'shish", "Добавить через Telegram", "Add via Telegram")} onClose={onClose}>
      {res ? (
        <div className="stack">
          <div className="note">{t.l("Havolani odamga yuboring. U botni ochadi → «Tasdiq kutmoqda»da paydo bo'ladi → tasdiqlang, login unga Telegram'da keladi. Havola 24 soat amal qiladi.",
            "Отправьте ссылку человеку. Он откроет бота → появится в «Ожидают подтверждения» → подтвердите, логин придёт ему в Telegram. Ссылка живёт 24 часа.", "")}</div>
          <input readOnly value={res.link} onFocus={(e) => e.target.select()} />
          <div className="row"><span className="spacer" />
            <button className="btn" onClick={() => navigator.clipboard?.writeText(res.link || "")}>{t.l("Nusxa olish", "Копировать", "Copy")}</button>
            <button className="btn primary" onClick={onClose}>OK</button></div>
        </div>
      ) : (
        <div className="stack">
          <label className="field">{t.l("Rol", "Роль", "Role")}<select value={role} onChange={(e) => setRole(e.target.value)}>
            {roles.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}</select></label>
          <label className="check"><input type="checkbox" checked={pay} onChange={(e) => setPay(e.target.checked)} />
            <span><b>{t.l("Oylikni ko'radi", "Видит зарплату", "Sees salary")}</b></span></label>
          <Err e={err} />
          <div className="row"><span className="spacer" />
            <button className="btn primary" disabled={!role} onClick={() => api<Invite>("/api/users/invite", { body: { role, can_see_payroll: pay } })
              .then(setRes).catch((x) => setErr(x.message))}>{t.l("Havola yaratish", "Создать ссылку", "Create link")}</button></div>
        </div>
      )}
    </Modal>
  );
}

export function UsersPage() {
  const t = useT();
  const { me, dicts, go } = usePanel();
  const users = useLoad<User[]>("/api/users");
  const roles = useLoad<Role[]>("/api/roles");
  const [invite, setInvite] = useState(false);
  const roleName = (c: string) => roles.data?.find((r) => r.code === c)?.name || c;
  const branches = (ids: number[] | null) => ids ? ids.map((i) => dicts.branches.find((b) => b.id === i)?.name || i).join(", ")
    : t.l("Butun tarmoq", "Вся сеть", "All branches");
  return (
    <>
      <div className="row page-intro">
        <span className="muted">{t.l("HR-panelga kiradiganlar: rol, filiallar, oylikni ko'rish", "Кто входит в HR-панель: роль, филиалы, доступ к зарплате", "")}</span>
        <span className="spacer" />
        <button className="btn" onClick={() => go("roles")}>{t.l("Rollar", "Роли", "Roles")}</button>
        <button className="btn primary" disabled={!roles.data} onClick={() => setInvite(true)}>+ {t.l("Telegram orqali qo'shish", "Добавить через Telegram", "Add via Telegram")}</button>
      </div>
      <Err e={users.error} />
      <section className="card">
        <div className="tbl-wrap"><table className="tbl">
          <thead><tr><th>{t.l("Foydalanuvchi", "Пользователь", "User")}</th><th>{t.l("Rol", "Роль", "Role")}</th><th>{t.l("Holat", "Статус", "Status")}</th>
            <th className="ph-hide">{t.l("Filiallar", "Филиалы", "Branches")}</th><th className="ph-hide">{t.l("Oylik", "Зарплата", "Salary")}</th>
            <th className="ph-hide">{t.l("Oxirgi kirish", "Последний вход", "Last login")}</th></tr></thead>
          <tbody>{(users.data || []).map((u) => (
            <tr key={u.id}>
              <td><span className="named"><span className="avatar">{initials(u.full_name || u.username)}</span>
                <span><b style={{ fontWeight: 600 }}>{u.full_name || u.username}</b>{u.username === me.username && <span className="muted"> ({t.l("siz", "вы", "you")})</span>}
                  <span className="sub">{u.username}{u.telegram_id ? ` · tg ${u.telegram_id}` : ""}</span></span></span></td>
              <td>{roleName(u.role)}</td>
              <td><span className={`badge ${u.active ? "b-ok" : "b-bad"}`}>{u.active ? t.l("Faol", "Активен", "Active") : t.l("O'chiq", "Отключён", "Off")}</span></td>
              <td className="ph-hide">{branches(u.branch_scope)}</td>
              <td className="ph-hide">{u.can_see_payroll || roles.data?.find((r) => r.code === u.role)?.perms.includes("*") ? t.l("Ko'radi", "Видит", "Sees") : "—"}</td>
              <td className="small muted ph-hide">{ago(t, u.last_login)}</td>
            </tr>
          ))}</tbody>
        </table>{users.data?.length === 0 && <Empty />}</div>
      </section>
      {invite && roles.data && <InviteModal roles={roles.data} onClose={() => setInvite(false)} />}
    </>
  );
}

export function PendingUsers() {
  const t = useT();
  const list = useLoad<Invite[]>("/api/users/pending");
  const [err, setErr] = useState<string | null>(null);
  const act = (i: Invite, a: "approve" | "reject") => api(`/api/users/pending/${i.id}/${a}`, { body: {} }).then(list.reload).catch((x) => setErr(x.message));
  const st: Record<string, string> = { open: t.l("havola yuborilgan", "ссылка отправлена", "sent"), pending: t.l("kutmoqda", "ожидает", "pending"),
    approved: t.l("tasdiqlangan", "подтверждён", "approved"), rejected: t.l("rad etilgan", "отклонён", "rejected"), expired: t.l("eskirgan", "истёк", "expired") };
  return (
    <>
      <p className="muted page-intro">{t.l("Telegram havolasi orqali kelganlar. Tasdiqlasangiz, login va parol ularga Telegram'da boradi.",
        "Пришедшие по Telegram-ссылке. После подтверждения логин и пароль уйдут им в Telegram.", "")}</p>
      <Err e={err || list.error} />
      <section className="card">
        <div className="tbl-wrap"><table className="tbl">
          <thead><tr><th>{t.l("Ism", "Имя", "Name")}</th><th>Telegram</th><th>{t.l("Rol", "Роль", "Role")}</th><th>{t.l("Holat", "Статус", "Status")}</th><th /></tr></thead>
          <tbody>{(list.data || []).map((i) => (
            <tr key={i.id}><td>{i.tg_name || "—"}<span className="sub">{t.l("yaratdi", "создал", "by")} {i.created_by.replace("user:", "")}</span></td>
              <td>{i.tg_username ? `@${i.tg_username}` : "—"}<span className="sub">{i.telegram_id || ""}</span></td>
              <td>{i.role}</td><td><span className={`badge ${i.status === "pending" ? "b-warn" : i.status === "approved" ? "b-ok" : ""}`}>{st[i.status] || i.status}</span></td>
              <td className="r">{(i.status === "pending" || i.status === "open") && <div className="row" style={{ justifyContent: "flex-end" }}>
                <button className="btn sm" onClick={() => act(i, "reject")}>{t.l("Rad etish", "Отклонить", "Reject")}</button>
                {i.status === "pending" && <button className="btn sm primary" onClick={() => act(i, "approve")}>{t.l("Tasdiqlash", "Подтвердить", "Approve")}</button>}
              </div>}</td></tr>
          ))}</tbody>
        </table>{list.data?.length === 0 && <Empty />}</div>
      </section>
    </>
  );
}

export function BotAccess() {
  const t = useT();
  const d = useDesc();
  const list = useLoad<BotUser[]>("/api/bot-access");
  const catalog = useLoad<Catalog>("/api/org/catalog");
  const [edit, setEdit] = useState<BotUser | null>(null);
  const [fns, setFns] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const fn = (c: string) => { const i = catalog.data?.bot_functions.find((x) => x.code === c); return i ? d(i) : c; };
  return (
    <>
      <p className="muted page-intro">{t.l("Agentlar bilan kim gaplasha oladi va qaysi funksiyalar ochiq", "Кто может общаться с агентами и какие функции открыты", "")}</p>
      <Err e={err || list.error} />
      <section className="card">
        <div className="tbl-wrap"><table className="tbl">
          <thead><tr><th>{t.l("Xodim", "Сотрудник", "Employee")}</th><th>{t.l("Funksiyalar", "Функции", "Functions")}</th><th className="ph-hide">{t.l("Oxirgi xabar", "Последнее сообщение", "Last message")}</th><th /></tr></thead>
          <tbody>{(list.data || []).map((u) => (
            <tr key={u.id}><td><span className="named"><span className="avatar">{initials(u.full_name)}</span>
              <span><b style={{ fontWeight: 600 }}>{u.full_name}</b><span className="sub">{[u.position, u.department].filter(Boolean).join(" · ")} · tg {u.telegram_id}</span></span></span></td>
              <td className="small">{u.functions.length ? u.functions.map(fn).join(", ") : <span className="muted">{t.l("hamma (rahbar/HR)", "все (руководитель/HR)", "all")}</span>}</td>
              <td className="small muted ph-hide">{ago(t, u.last_message)}</td>
              <td className="r"><button className="btn sm" disabled={!catalog.data} onClick={() => { setEdit(u); setFns(u.functions); }}><Ic n="key" /></button></td></tr>
          ))}</tbody>
        </table>{list.data?.length === 0 && <Empty />}</div>
      </section>
      {edit && catalog.data && <Modal title={edit.full_name} onClose={() => setEdit(null)}>
        <div className="stack">
          <Checks items={catalog.data.bot_functions} value={fns} onChange={setFns} />
          <div className="row"><span className="spacer" />
            <button className="btn primary" onClick={() => api(`/api/employees/${edit.id}/functions`, { body: { functions: fns } })
              .then(() => { setEdit(null); list.reload(); }).catch((x) => setErr(x.message))}>{t("save")}</button></div>
        </div>
      </Modal>}
    </>
  );
}
