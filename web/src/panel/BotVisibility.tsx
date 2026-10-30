import { useEffect, useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import { Err, useLoad } from "../ui";

type Cat = { uz: string; ru: string };
type Row = { group: string[]; private: string[] };
type Cfg = {
  categories: Record<string, Cat>; channels: string[]; roles: string[];
  people: { tg_id: number; name: string; role: string }[];
  settings: { roles: Record<string, Row>; people: Record<string, Row & { name: string }>; group_report_names: boolean };
};

/** Who sees what in the bot: in the HR group (👥) and in private chat (👤), per bot role with per-person exceptions. */
export function BotVisibility() {
  const t = useT();
  const cfg = useLoad<Cfg>("/api/bot-visibility");
  const [s, setS] = useState<Cfg["settings"] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (cfg.data) setS(structuredClone(cfg.data.settings)); }, [cfg.data]);
  if (!cfg.data || !s) return <Err e={cfg.error} />;
  const cats = Object.keys(cfg.data.categories);
  const catName = (c: string) => t.l(cfg.data!.categories[c].uz, cfg.data!.categories[c].ru, cfg.data!.categories[c].uz);
  const ROLE: Record<string, string> = { owner: t.l("Egasi", "Владелец", "Owner"), hr_head: "HR", manager: t.l("Rahbar", "Руководитель", "Manager"),
    employee: t.l("Xodim", "Сотрудник", "Employee") };
  const toggle = (row: Row, ch: "group" | "private", c: string) => {
    const set = new Set(row[ch]); set.has(c) ? set.delete(c) : set.add(c); row[ch] = [...set]; setS({ ...s });
  };
  const cells = (row: Row) => cats.map((c) => (
    <td key={c} style={{ whiteSpace: "nowrap", textAlign: "center" }}>
      <label title={t.l("Guruhda", "В группе", "In group")} style={{ marginRight: 6 }}>
        <input type="checkbox" checked={row.group.includes(c)} onChange={() => toggle(row, "group", c)} /> 👥</label>
      <label title={t.l("Shaxsiy chatda", "В личке", "Private chat")}>
        <input type="checkbox" checked={row.private.includes(c)} onChange={() => toggle(row, "private", c)} /> 👤</label>
    </td>));
  return (
    <div className="card">
      <div className="card-h"><span className="card-t">{t.l("Botda kim nimani ko'radi", "Кто что видит в боте", "Who sees what in the bot")}</span>
        <span className="card-s">{t.l("👥 HR guruhida · 👤 shaxsiy chatda. Belgi olib tashlansa, agent bu ma'lumotni o'sha joyda ko'rsatmaydi.",
          "👥 в HR-группе · 👤 в личке. Без галочки агент не показывает эти данные там.", "👥 HR group · 👤 private chat.")}</span>
        <span className="card-a"><button className="btn sm primary" onClick={async () => {
          setErr(null);
          try { await api("/api/bot-visibility", { method: "PUT", body: s }); setMsg(t.l("Saqlandi", "Сохранено", "Saved")); cfg.reload(); }
          catch (x: any) { setErr(x.message); }
        }}>{t("save")}</button></span></div>
      <Err e={err} />{msg && <div className="note small">{msg}</div>}
      <div className="table-wrap"><table>
        <thead><tr><th>{t.l("Kim", "Кто", "Who")}</th>{cats.map((c) => <th key={c} className="small">{catName(c)}</th>)}</tr></thead>
        <tbody>
          {cfg.data.roles.map((r) => <tr key={r}><td><b>{ROLE[r] || r}</b> <span className="muted small">{t.l("(rol)", "(роль)", "(role)")}</span></td>{cells(s.roles[r])}</tr>)}
          {cfg.data.people.map((p) => {
            const key = String(p.tg_id), own = s.people[key];
            return <tr key={key}>
              <td>{p.name || key} <span className="muted small">· {ROLE[p.role] || p.role}</span><br />
                <select className="ctl" value={own ? "own" : "role"} onChange={(e) => {
                  if (e.target.value === "own") s.people[key] = { name: p.name, ...structuredClone(s.roles[p.role] || { group: cats, private: cats }) };
                  else delete s.people[key];
                  setS({ ...s });
                }}>
                  <option value="role">{t.l("Rol bo'yicha", "Как у роли", "As role")}</option>
                  <option value="own">{t.l("Alohida sozlash", "Отдельно", "Custom")}</option>
                </select></td>
              {own ? cells(own) : cats.map((c) => <td key={c} className="muted small" style={{ textAlign: "center" }}>—</td>)}
            </tr>;
          })}
        </tbody>
      </table></div>
      <label className="row small" style={{ marginTop: 10 }}>
        <input type="checkbox" checked={s.group_report_names} onChange={(e) => setS({ ...s, group_report_names: e.target.checked })} />
        {t.l("Guruh hisobotlarida ism va summalar (masalan, kim qancha jarima oldi)",
          "Имена и суммы в отчётах группы (например, кто сколько штрафов получил)", "Names and amounts in group reports")}
      </label>
    </div>
  );
}
