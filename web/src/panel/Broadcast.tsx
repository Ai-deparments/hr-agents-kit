import { useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import { Err, useLoad } from "../ui";
import { usePanel } from "./ctx";

type Emp = { id: number; full_name: string; branch: string | null; department: string | null; telegram_linked: boolean };

export default function Broadcast() {
  const t = useT();
  const { dicts } = usePanel();
  const [mode, setMode] = useState<"dept" | "branch" | "people">("dept");
  const [deptId, setDeptId] = useState<number | "">("");
  const [branchId, setBranchId] = useState<number | "">("");
  const [ids, setIds] = useState<number[]>([]);
  const [q, setQ] = useState("");
  const [text, setText] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const emps = useLoad<Emp[]>(mode === "people" ? `/api/employees?q=${encodeURIComponent(q)}` : null, [q, mode]);
  const stats = useLoad<{ pending: number; failed: number }>("/api/outbox/stats");
  const ready = text.trim().length >= 3 && (mode === "dept" ? !!deptId : mode === "branch" ? !!branchId : ids.length > 0);

  return (
    <div className="grid two">
      <div className="card stack">
        <div className="card-h"><span className="card-t">{t("broadcast")}</span>
          <span className="card-s">{t.l("Bot orqali faqat Telegram'i ulangan xodimlarga", "Через бота, только сотрудникам с привязанным Telegram", "Via the bot, only to employees with linked Telegram")}</span></div>
        <label className="field">{t.l("Kimga", "Кому", "Recipients")}
          <select value={mode} onChange={(e) => setMode(e.target.value as "dept" | "branch" | "people")}>
            <option value="dept">{t("departments")}</option>
            <option value="branch">{t("branches")}</option>
            <option value="people">{t("employees")}</option>
          </select>
        </label>
        {mode === "dept" && <select value={deptId} onChange={(e) => setDeptId(Number(e.target.value) || "")}>
          <option value="">—</option>{dicts.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>}
        {mode === "branch" && <select value={branchId} onChange={(e) => setBranchId(Number(e.target.value) || "")}>
          <option value="">—</option>{dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select>}
        {mode === "people" && <>
          <input placeholder={t("search")} value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="checks" style={{ maxHeight: 260, overflowY: "auto" }}>
            {(emps.data || []).filter((e) => e.telegram_linked).map((e) => (
              <label key={e.id} className="check"><input type="checkbox" checked={ids.includes(e.id)}
                onChange={(x) => setIds(x.target.checked ? [...ids, e.id] : ids.filter((i) => i !== e.id))} />
                <span><b>{e.full_name}</b><span>{e.branch} · {e.department || "—"}</span></span></label>
            ))}
          </div>
        </>}
        <label className="field">{t.l("Xabar", "Сообщение", "Message")}<textarea rows={6} maxLength={3500} value={text} onChange={(e) => setText(e.target.value)} /></label>
        <Err e={err} />
        {msg && <div className="note">{msg}</div>}
        <div className="row"><span className="spacer" />
          <button className="btn primary" disabled={!ready} onClick={async () => {
            setErr(null); setMsg(null);
            try {
              const r = await api<{ queued: number }>("/api/broadcast", { body: { text,
                department_id: mode === "dept" ? deptId : null, branch_id: mode === "branch" ? branchId : null,
                employee_ids: mode === "people" ? ids : [] } });
              setMsg(`${t.l("Navbatga qo'yildi", "В очереди", "Queued")}: ${r.queued}`); setText(""); stats.reload();
            } catch (x: any) { setErr(x.message); }
          }}>{t("send")}</button>
        </div>
      </div>
      <div className="card kpi-group" style={{ alignSelf: "start" }}>
        <div className="kpi"><span className="kpi-l">{t.l("Navbatda", "В очереди", "Queued")}</span><span className="kpi-v">{stats.data?.pending ?? "—"}</span></div>
        <div className="kpi"><span className="kpi-l">{t.l("Yetkazilmadi", "Не доставлено", "Not delivered")}</span><span className="kpi-v">{stats.data?.failed ?? "—"}</span>
          <span className="kpi-f">{t.l("bot bloklangan yoki /start bosilmagan", "бот заблокирован или нет /start", "bot blocked or /start not pressed")}</span></div>
      </div>
    </div>
  );
}
