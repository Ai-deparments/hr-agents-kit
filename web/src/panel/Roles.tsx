import { Check } from "lucide-react";
import { useState } from "react";
import { BotVisibility } from "./BotVisibility";
import { api, dash } from "../api";
import { useT } from "../i18n";
import { Empty, Err, Modal, useLoad } from "../ui";
import { usePanel } from "./ctx";
import { Catalog, Checks, useDesc } from "./Registrations";

type Role = { id: number; code: string; name: string; description: string; perms: string[]; system: boolean; users: number };
type User = { id: number; username: string; full_name: string; role: string; branch_scope: number[] | null; can_see_payroll: boolean; active: boolean };

function RoleEditor({ role, catalog, onClose, onDone }: { role: Role | null; catalog: Catalog; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const [name, setName] = useState(role?.name || "");
  const [description, setDescription] = useState(role?.description || "");
  const [perms, setPerms] = useState<string[]>(role?.perms || ["hr.read"]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={role ? role.name : `${t("add")}: ${t.l("rol", "роль", "role")}`} onClose={onClose}>
      <div className="stack" style={{ minWidth: 0 }}>
        <label className="field">{t("name")}<input value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="field">{t("description")}<textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
        <h2 style={{ margin: "4px 0 0" }}>{t.l("Nima qila oladi", "Что может делать", "What it can do")}</h2>
        <Checks items={catalog.permissions} value={perms} onChange={setPerms} />
        <Err e={err} />
        <div className="row"><span className="spacer" />
          <button className="btn" onClick={onClose}>{t("cancel")}</button>
          <button className="btn primary" disabled={busy || name.trim().length < 2} onClick={async () => {
            setBusy(true);
            try {
              const body = { name, description, perms };
              await (role ? api(`/api/roles/${role.id}`, { method: "PATCH", body }) : api("/api/roles", { body }));
              onDone(); onClose();
            } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
          }}>{t("save")}</button>
        </div>
      </div>
    </Modal>
  );
}

function UserEditor({ user, roles, onClose, onDone }: { user: User | null; roles: Role[]; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const { dicts } = usePanel();
  const [f, setF] = useState({ username: user?.username || "", full_name: user?.full_name || "", password: "",
    role: user?.role || roles.find((r) => !r.perms.includes("*"))?.code || "", can_see_payroll: user?.can_see_payroll || false,
    active: user?.active ?? true, branches: user?.branch_scope || [] as number[] });
  const [err, setErr] = useState<string | null>(null);
  const isMain = user?.username === "admin";
  return (
    <Modal title={user ? user.username : `${t("add")}: ${t("users")}`} onClose={onClose}>
      <div className="stack">
        {!user && <label className="field">{t("username")}<input value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></label>}
        <label className="field">{t.l("Ism-familiya", "ФИО", "Full name")}<input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></label>
        <label className="field">{t("password")}{user ? ` (${t.l("yangi", "новый", "new")})` : ""}
          <input type="password" minLength={10} value={f.password} placeholder="≥ 10" onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
        <label className="field">{t.l("Rol", "Роль", "Role")}
          <select value={f.role} disabled={isMain} onChange={(e) => setF({ ...f, role: e.target.value })}>
            {roles.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
          </select>
        </label>
        <label className="field">{t("branches")} ({t.l("bo'sh = hammasi", "пусто = все", "empty = all")})
          <select multiple size={Math.min(6, dicts.branches.length)} value={f.branches.map(String)}
            onChange={(e) => setF({ ...f, branches: [...e.target.selectedOptions].map((o) => Number(o.value)) })} style={{ height: "auto" }}>
            {dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
        <label className="check"><input type="checkbox" checked={f.can_see_payroll} onChange={(e) => setF({ ...f, can_see_payroll: e.target.checked })} />
          <span><b>{t.l("Oylik summalarini ko'radi", "Видит суммы ЗП", "Sees salary amounts")}</b></span></label>
        {user && !isMain && <label className="check"><input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} />
          <span><b>{t.l("Faol", "Активен", "Active")}</b></span></label>}
        <Err e={err} />
        <div className="row"><span className="spacer" />
          <button className="btn" onClick={onClose}>{t("cancel")}</button>
          <button className="btn primary" onClick={async () => {
            const body: Record<string, unknown> = { full_name: f.full_name, role: f.role, can_see_payroll: f.can_see_payroll,
              branch_scope: f.branches.length ? f.branches : null };
            if (f.password) body.password = f.password;
            try {
              if (user) await api(`/api/users/${user.id}`, { method: "PATCH", body: { ...body, ...(isMain ? {} : { active: f.active }) } });
              else await api("/api/users", { body: { ...body, username: f.username } });
              onDone(); onClose();
            } catch (x: any) { setErr(x.message); }
          }}>{t("save")}</button>
        </div>
      </div>
    </Modal>
  );
}

export default function Roles() {
  const t = useT();
  const d = useDesc();
  const { dicts } = usePanel();
  const roles = useLoad<Role[]>("/api/roles");
  const users = useLoad<User[]>("/api/users");
  const catalog = useLoad<Catalog>("/api/org/catalog");
  const [role, setRole] = useState<Role | "new" | null>(null);
  const [user, setUser] = useState<User | "new" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const permName = (c: string) => { const i = catalog.data?.permissions.find((x) => x.code === c); return i ? d(i) : c === "*" ? t.l("To'liq ruxsat", "Полный доступ", "Full access") : c; };
  const roleName = (c: string) => roles.data?.find((r) => r.code === c)?.name || c;
  const branchNames = (ids: number[] | null) => ids ? ids.map((i) => dicts.branches.find((b) => b.id === i)?.name || i).join(", ") : t.l("Hammasi", "Все", "All");

  return (
    <div className="stack">
      <Err e={roles.error || users.error || err} />
      <div className="card">
        <div className="card-h"><span className="card-t">{t("roles")}</span>
          <span className="card-s">{t.l("Har bir rol nima qila olishi aniq yozilgan", "Для каждой роли расписано, что она может", "Each role lists exactly what it can do")}</span>
          <span className="card-a"><button className="btn sm primary" disabled={!catalog.data} onClick={() => setRole("new")}>+ {t("add")}</button></span></div>
        <div className="grid two">
          {(roles.data || []).map((r) => (
            <div key={r.id} className="card" style={{ boxShadow: "none" }}>
              <div className="card-h"><span className="card-t">{r.name}</span>
                <span className="card-s">{r.code} · {r.users} {t.l("foydalanuvchi", "польз.", "users")}{r.system ? ` · ${t.l("tizim", "системная", "system")}` : ""}</span>
                <span className="card-a">{!r.perms.includes("*") && <button className="btn sm" disabled={!catalog.data} onClick={() => setRole(r)}>{t("edit")}</button>}
                  {!r.system && <button className="btn sm danger" disabled={r.users > 0}
                    onClick={() => api(`/api/roles/${r.id}`, { method: "DELETE" }).then(roles.reload).catch((x) => setErr(x.message))}>{t("delete")}</button>}</span></div>
              {r.description && <p className="small muted" style={{ marginBottom: 8 }}>{r.description}</p>}
              <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                {r.perms.map((p) => <li key={p}>{permName(p)}</li>)}
              </ul>
            </div>
          ))}
        </div>
      </div>
      <div className="card">
        <div className="card-h"><span className="card-t">{t("users")}</span>
          <span className="card-a"><button className="btn sm primary" disabled={!roles.data} onClick={() => setUser("new")}>+ {t("add")}</button></span></div>
        <div className="table-wrap"><table>
          <thead><tr><th>{t("username")}</th><th>{t.l("Ism-familiya", "ФИО", "Full name")}</th><th>{t.l("Rol", "Роль", "Role")}</th><th>{t("branches")}</th><th>{t.l("Oylik", "ЗП", "Salary")}</th><th>{t.l("Holat", "Статус", "Status")}</th><th></th></tr></thead>
          <tbody>{(users.data || []).map((u) => (
            <tr key={u.id}><td>{u.username}</td><td>{dash(u.full_name)}</td><td>{roleName(u.role)}</td><td className="small">{branchNames(u.branch_scope)}</td>
              <td>{u.can_see_payroll ? <Check className="ic inl" size={14} aria-hidden="true" /> : "—"}</td><td><span className={`badge ${u.active ? "b-ok" : ""}`}>{u.active ? t.l("faol", "активен", "active") : t.l("o'chiq", "отключён", "disabled")}</span></td>
              <td className="num"><button className="btn sm" disabled={!roles.data} onClick={() => setUser(u)}>{t("edit")}</button></td></tr>
          ))}</tbody>
        </table>{users.data?.length === 0 && <Empty />}</div>
      </div>
      <BotVisibility />
      {role && catalog.data && <RoleEditor role={role === "new" ? null : role} catalog={catalog.data} onClose={() => setRole(null)} onDone={roles.reload} />}
      {user && roles.data && <UserEditor user={user === "new" ? null : user} roles={roles.data} onClose={() => setUser(null)}
        onDone={() => { users.reload(); roles.reload(); }} />}
    </div>
  );
}
