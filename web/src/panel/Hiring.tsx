import { CalendarDays, FileText } from "lucide-react";
import { useState } from "react";
import { api, dash } from "../api";
import { useT } from "../i18n";
import { Empty, Err, Modal, useLoad } from "../ui";
import { usePanel } from "./ctx";

const fmt = (s: string) => new Date(s).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

/** Interview slots HR offers; the candidate picks one in the bot by number. */
export function SlotsCard({ write }: { write: boolean }) {
  const t = useT();
  const slots = useLoad<any[]>("/api/slots", []);
  const [adding, setAdding] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 10 }}><h2 style={{ margin: 0 }}>{t.l("Suhbat vaqtlari", "Слоты собеседований", "Interview slots")}</h2>
        <span className="spacer" />{write && <button className="btn primary" onClick={() => setAdding(true)}>+ {t.l("Vaqt qo'shish", "Добавить время", "Add times")}</button>}</div>
      <Err e={err || slots.error} />
      <div className="table-wrap"><table>
        <thead><tr><th>{t.l("Vaqt", "Время", "Time")}</th><th>{t.l("Joy", "Место", "Place")}</th><th>{t.l("Suhbatdosh", "Интервьюер", "Interviewer")}</th>
          <th>{t("c_status")}</th><th>{t.l("Nomzod", "Кандидат", "Candidate")}</th><th /></tr></thead>
        <tbody>{slots.data?.filter((s) => s.status !== "cancelled").map((s) => (
          <tr key={s.id}><td className="num"><b>{fmt(s.starts_at)}</b> <span className="muted small">{s.minutes}′</span></td>
            <td className="small">{dash(s.place)}</td><td className="small">{dash(s.interviewer)}</td>
            <td><span className={`badge ${s.status === "booked" ? "b-ok" : "b-info"}`}>{s.status === "booked" ? t.l("Band", "Занят", "Booked") : t.l("Bo'sh", "Свободен", "Free")}</span></td>
            <td>{dash(s.candidate)}</td>
            <td>{write && <button className="btn sm danger" onClick={async () => {
              try { await api(`/api/slots/${s.id}`, { method: "DELETE" }); slots.reload(); } catch (x: any) { setErr(x.message); }
            }}>{t.l("Bekor", "Отменить", "Cancel")}</button>}</td></tr>
        ))}</tbody>
      </table></div>
      {slots.data?.filter((s) => s.status !== "cancelled").length === 0 && <Empty />}
      {adding && <AddSlots onClose={() => setAdding(false)} onDone={() => { setAdding(false); slots.reload(); }} />}
    </div>
  );
}

function AddSlots({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const t = useT();
  const tomorrow = new Date(Date.now() + 864e5).toISOString().slice(0, 10);
  const [f, setF] = useState<any>({ day: tomorrow, times: "10:00, 10:30, 11:00", minutes: 30, place: "", interviewer: "" });
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal title={t.l("Suhbat vaqtlari", "Слоты собеседований", "Interview slots")} onClose={onClose}>
      <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api("/api/slots", { body: { ...f, minutes: Number(f.minutes), times: f.times.split(/[,\s]+/).filter(Boolean) } });
          onDone();
        } catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">{t.l("Kun", "День", "Day")}<input type="date" required value={f.day} onChange={set("day")} /></label>
        <label className="field">{t.l("Vaqtlar (vergul bilan)", "Время (через запятую)", "Times (comma separated)")}<input required value={f.times} onChange={set("times")} /></label>
        <label className="field">{t.l("Davomiyligi", "Длительность", "Duration")}<select value={f.minutes} onChange={set("minutes")}>
          {[15, 30, 45, 60, 90].map((m) => <option key={m} value={m}>{m} {t.l("daq", "мин", "min")}</option>)}</select></label>
        <label className="field">{t.l("Joy yoki havola", "Место или ссылка", "Place or link")}<input value={f.place} onChange={set("place")} /></label>
        <label className="field">{t.l("Suhbatdosh", "Интервьюер", "Interviewer")}<input value={f.interviewer} onChange={set("interviewer")} /></label>
        <Err e={err} />
        <button className="btn primary">{t("save")}</button>
      </form>
    </Modal>
  );
}

/** Invite / Reject: HR sees the exact message the candidate will get; it is sent once, only after "Send". */
export function DecisionPreview({ cand, action, onClose, onDone }: { cand: any; action: "invite" | "reject"; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const p = useLoad<any>(`/api/candidates/${cand.id}/preview?action=${action}`);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const title = action === "invite" ? t.l("Suhbatga taklif", "Приглашение на собеседование", "Invite to interview") : t.l("Rad etish", "Отказ", "Reject");
  const canSend = action === "reject" || (p.data?.telegram && p.data?.text);
  return (
    <Modal title={`${title} · ${cand.full_name}`} onClose={onClose}>
      <div className="stack">
        <Err e={p.error || err} />
        {p.data && !p.data.telegram && <div className="note">{action === "reject"
          ? t.l("Telegram yo'q — holat o'zgaradi, xabar yuborilmaydi.", "Нет Telegram — статус изменится, сообщение не уйдёт.", "No Telegram — the status changes, no message is sent.")
          : t.l("Nomzodning Telegram'i yo'q — bot orqali yuborib bo'lmaydi.", "У кандидата нет Telegram — через бота не отправить.", "No Telegram — can't send via the bot.")}</div>}
        {p.data && action === "invite" && !p.data.text && <div className="note">{t.l("Bo'sh vaqt yo'q — avval suhbat vaqtlarini qo'shing.", "Нет свободных слотов — сначала добавьте время.", "No free slots — add interview times first.")}</div>}
        {p.data?.text && p.data.telegram && <>
          <div className="muted small">{t.l("Nomzod aynan shu xabarni oladi:", "Кандидат получит ровно это сообщение:", "The candidate gets exactly this message:")}</div>
          <pre className="ad-preview">{p.data.text}</pre>
        </>}
        <div className="row"><span className="spacer" />
          <button className="btn" onClick={onClose}>{t("cancel")}</button>
          <button className={`btn ${action === "reject" ? "danger" : "primary"}`} disabled={!p.data || !canSend || busy} onClick={async () => {
            setBusy(true); setErr(null);
            try { await api(`/api/candidates/${cand.id}/${action}`, { body: { expected_text: p.data.text } }); onDone(); onClose(); }
            catch (x: any) { setErr(x.message); p.reload(); } finally { setBusy(false); }
          }}>{action === "reject" ? t.l("Rad etish", "Отказать", "Reject") : t.l("Yuborish", "Отправить", "Send")}</button>
        </div>
      </div>
    </Modal>
  );
}

/** Inside the candidate card: interview invite (slots in the bot) and job offer (accepted in words). */
export function CandidateHiring({ cand, write, onChanged }: { cand: any; write: boolean; onChanged: () => void }) {
  const t = useT();
  const { dicts } = usePanel();
  const st = useLoad<any>(`/api/candidates/${cand.id}/steps`);
  const [offer, setOffer] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [f, setF] = useState<any>({ position_id: "", branch_id: "", salary_text: "", start_date: "", note: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  const d = st.data;
  if (!d) return <Err e={st.error} />;
  const STEP: Record<string, string> = { slots: t.l("Suhbatga taklif", "Приглашение", "Invite"), offer: t.l("Ish taklifi", "Оффер", "Offer") };
  const STATE: Record<string, string> = { open: t.l("Javob kutilmoqda", "Ждём ответ", "Waiting"), done: t.l("Qabul qilindi", "Принято", "Accepted"),
    declined: t.l("Rad etdi", "Отказ", "Declined"), cancelled: t.l("Bekor", "Отменено", "Cancelled") };
  return (
    <div className="stack" style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
      <b>{t.l("Yollash bosqichlari", "Этапы найма", "Hiring steps")}</b>
      {!d.telegram && <div className="note">{t.l("Nomzodning Telegram'i yo'q — bot orqali yuborib bo'lmaydi.", "У кандидата нет Telegram — через бота не отправить.", "No Telegram — can't send via the bot.")}</div>}
      {d.interview && <div className="small"><CalendarDays className="ic inl" size={14} aria-hidden="true" /> {t.l("Suhbat", "Собеседование", "Interview")}: <b>{fmt(d.interview.starts_at)}</b> {d.interview.place && `· ${d.interview.place}`}</div>}
      {d.steps.map((s: any) => <div key={s.id} className="row small"><span>{STEP[s.kind] || s.kind}</span><span className="spacer" />
        <span className={`badge ${s.status === "done" ? "b-ok" : s.status === "open" ? "b-warn" : "b-bad"}`}>{STATE[s.status] || s.status}</span>
        <span className="muted">{fmt(s.created_at)}</span></div>)}
      {msg && <div className="note">{msg}</div>}
      <Err e={err} />
      {write && d.telegram && cand.status !== "hired" && !offer && <div className="row">
<<<<<<< HEAD
        <button className="btn" onClick={() => setInviting(true)}>🗓 {t.l("Suhbatga taklif", "Пригласить на собеседование", "Invite to interview")}</button>
        <button className="btn primary" onClick={() => setOffer(true)}>📄 {t.l("Ish taklifi", "Отправить оффер", "Send offer")}</button>
=======
        <button className="btn" onClick={async () => {
          try { const r = await api<any>(`/api/candidates/${cand.id}/invite`, { body: {} }); setMsg(t.l(`Yuborildi: ${r.offered} ta vaqt`, `Отправлено: ${r.offered} слотов`, `Sent ${r.offered} slots`)); st.reload(); }
          catch (x: any) { setErr(x.message); }
        }}><CalendarDays className="ic inl" size={14} aria-hidden="true" /> {t.l("Suhbatga taklif", "Пригласить на собеседование", "Invite to interview")}</button>
        <button className="btn primary" onClick={() => setOffer(true)}><FileText className="ic inl" size={14} aria-hidden="true" /> {t.l("Ish taklifi", "Отправить оффер", "Send offer")}</button>
>>>>>>> 13bd074 (feat(web): lucide-react icons and react-bits CountUp instead of hand-drawn icons and emoji)
      </div>}
      {offer && <form className="form" onSubmit={async (e) => {
        e.preventDefault();
        try {
          await api(`/api/candidates/${cand.id}/offer`, { body: { ...f, position_id: f.position_id ? Number(f.position_id) : null,
            branch_id: f.branch_id ? Number(f.branch_id) : null } });
          setOffer(false); setMsg(t.l("Taklif yuborildi. Nomzod «qabul qilaman» deb yozsa — xodim kartasi ochiladi.",
            "Оффер отправлен. Кандидат пишет «qabul qilaman» → откроется карточка сотрудника.", "Offer sent.")); st.reload(); onChanged();
        } catch (x: any) { setErr(x.message); }
      }}>
        <label className="field">{t("c_position")}<select value={f.position_id} onChange={set("position_id")}><option value="">—</option>
          {dicts.positions.map((p: any) => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
        <label className="field">{t("c_branch")}<select value={f.branch_id} onChange={set("branch_id")}><option value="">—</option>
          {dicts.branches.map((b: any) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
        <label className="field">{t("rc_salaryLabel")}<input required value={f.salary_text} onChange={set("salary_text")} placeholder="6 000 000 so'm" /></label>
        <label className="field">{t.l("Ish boshlanishi", "Дата выхода", "Start date")}<input type="date" required value={f.start_date} onChange={set("start_date")} /></label>
        <label className="field">{t.l("Izoh", "Примечание", "Note")}<textarea rows={2} value={f.note} onChange={set("note")} /></label>
        <div className="row"><button type="button" className="btn" onClick={() => setOffer(false)}>{t("cancel")}</button>
          <button className="btn primary">{t.l("Yuborish", "Отправить", "Send")}</button></div>
      </form>}
      {inviting && <DecisionPreview cand={cand} action="invite" onClose={() => setInviting(false)}
        onDone={() => { setMsg(t.l("Taklif yuborildi.", "Приглашение отправлено.", "Invite sent.")); st.reload(); }} />}
    </div>
  );
}
