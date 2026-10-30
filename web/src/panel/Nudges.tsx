import { useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import { Err, useLoad } from "../ui";

/** Weekly discipline reminders: drafted on Monday, sent to employees only after HR approves (text is editable). */
export function Nudges() {
  const t = useT();
  const list = useLoad<any[]>("/api/nudges", []);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [edit, setEdit] = useState<Record<number, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const rows = list.data || [];
  const run = async (f: () => Promise<any>) => { setErr(null); try { await f(); list.reload(); } catch (x: any) { setErr(x.message); } };
  if (!rows.length && !msg) return null;
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>{t.l("Intizom eslatmalari", "Напоминания о дисциплине", "Discipline reminders")}</h2>
        <span className="badge b-warn">{rows.length}</span><span className="spacer" />
        <button className="btn primary" disabled={!sel.size} onClick={() => run(async () => {
          for (const id of sel) if (edit[id] !== undefined) await api(`/api/nudges/${id}`, { method: "PATCH", body: { text: edit[id] } });
          const r = await api<any>("/api/nudges/send", { body: { ids: [...sel] } });
          setMsg(t.l(`Yuborildi: ${r.sent}`, `Отправлено: ${r.sent}`, `Sent: ${r.sent}`)); setSel(new Set());
        })}>{t.l("Tanlanganlarni yuborish", "Отправить выбранные", "Send selected")} ({sel.size})</button>
      </div>
      <div className="note small" style={{ marginBottom: 8 }}>{t.l("O'tgan hafta 2+ kun kechikkanlar. Siz tasdiqlamaguningizcha hech kimga yuborilmaydi.",
        "Опоздали 2+ дня за прошлую неделю. Без вашего подтверждения никому не уходит.", "Late 2+ days last week. Nothing is sent without your approval.")}</div>
      {msg && <div className="note">{msg}</div>}
      <Err e={err || list.error} />
      <div className="stack">{rows.map((n) => (
        <div key={n.id} className="row" style={{ alignItems: "flex-start", gap: 10, borderTop: "1px solid var(--border)", paddingTop: 8 }}>
          <input type="checkbox" checked={sel.has(n.id)} onChange={(e) => {
            const s = new Set(sel); e.target.checked ? s.add(n.id) : s.delete(n.id); setSel(s);
          }} />
          <div style={{ flex: 1 }}>
            <div className="row small"><b>{n.employee}</b><span className="muted">{n.late_days} {t.l("kun", "дн.", "days")} · {n.late_min} {t.l("daq", "мин", "min")}</span></div>
            <textarea rows={3} style={{ width: "100%" }} value={edit[n.id] ?? n.text} onChange={(e) => setEdit({ ...edit, [n.id]: e.target.value })} />
          </div>
          <button className="btn sm" onClick={() => run(() => api(`/api/nudges/${n.id}/skip`, { method: "POST" }))}>{t.l("O'tkazib yuborish", "Пропустить", "Skip")}</button>
        </div>
      ))}</div>
    </div>
  );
}

/** Rule: late N times this month -> private Telegram message to the owner (and HR). Counting starts when turned on. */
export function LatenessRule() {
  const t = useT();
  const d = useLoad<any>("/api/nudges/lateness-rule", []);
  const [f, setF] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const r = f || d.data?.rule;
  if (!r) return <Err e={d.error} />;
  const over: any[] = d.data?.over_limit || [];
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>{t.l("Kechikish qoidasi", "Правило опозданий", "Lateness rule")}</h2>
        <span className={`badge ${r.enabled ? "b-ok" : ""}`}>{r.enabled ? t.l("yoqilgan", "включено", "on") : t.l("o'chiq", "выключено", "off")}</span>
      </div>
      <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
        <label className="row small"><input type="checkbox" checked={r.enabled} onChange={(e) => setF({ ...r, enabled: e.target.checked })} />
          {t.l("Xodim oyda", "Если сотрудник за месяц опоздал", "If an employee is late")}</label>
        <input type="number" min={1} max={31} style={{ width: 64 }} value={r.late_count} onChange={(e) => setF({ ...r, late_count: Number(e.target.value) })} />
        <span className="small">{t.l("marta kech qolsa, xabar yuborilsin:", "раз — написать:", "times — message:")}</span>
        <select className="ctl" value={r.to} onChange={(e) => setF({ ...r, to: e.target.value })}>
          <option value="owner">{t.l("Egasiga (shaxsiy)", "Владельцу (в личку)", "Owner (private)")}</option>
          <option value="owner_hr">{t.l("Egasi va HR ga", "Владельцу и HR", "Owner and HR")}</option>
        </select>
        <button className="btn sm primary" onClick={async () => {
          setErr(null);
          try { await api("/api/nudges/lateness-rule", { method: "PUT", body: r }); setF(null); d.reload(); setMsg(t.l("Saqlandi", "Сохранено", "Saved")); }
          catch (x: any) { setErr(x.message); }
        }}>{t("save")}</button>
      </div>
      <div className="note small" style={{ marginTop: 8 }}>{t.l(
        "Chegaraga yetganda (3, 6, 9…) bir marta yoziladi. Yoqilgan paytda chegaradan o'tganlar qayta yuborilmaydi; yangi oy noldan boshlanadi.",
        "Сообщение — при достижении порога (3, 6, 9…). Кто уже превысил порог на момент включения, повторно не сообщается; новый месяц — с нуля.",
        "One message per threshold (3, 6, 9…).")}</div>
      {msg && <div className="note small">{msg}</div>}
      <Err e={err} />
      {over.length > 0 && <div className="small" style={{ marginTop: 8 }}><b>{t.l("Bu oy chegaradan o'tganlar", "Превысили порог в этом месяце", "Over the limit this month")}:</b>{" "}
        {over.map((o) => `${o.full_name} (${o.late_days})`).join(", ")}</div>}
    </div>
  );
}
