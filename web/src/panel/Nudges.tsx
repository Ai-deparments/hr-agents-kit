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
