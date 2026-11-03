import { CalendarDays, Check, ExternalLink, FileText, Link, Play } from "lucide-react";
import { useContext, useMemo, useState } from "react";
import { api, download } from "../api";
import { LangCtx, useT } from "../i18n";
import { Ic } from "../icons";
import { Empty, Err, Modal, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

type Mat = { id: number; title: string; description: string; kind: string; filename: string | null; url: string | null; size: number;
  created_by: string; created_at: string; sent: number; planned: number; viewed: number; talks: number; talks_done: number;
  position_ids: number[]; department_ids: number[]; day_offset: number; for_new: boolean };
type PlanItem = { material_id: number; title: string; kind: string; day: number; reason: string; source: string };
type Progress = { employee: string; telegram: boolean; items: { id: number; title: string; kind: string; scheduled_for: string | null;
  sent_at: string | null; viewed_at: string | null; reason: string | null }[] };
type Emp = { id: number; full_name: string; branch: string | null; branch_id: number | null; department_id: number | null;
  department: string | null; position: string | null; telegram_linked: boolean; status: string };
type Send = { id: number; full_name: string; branch: string | null; telegram: boolean; sent_at: string; talk_at: string | null;
  talk_with: string | null; talk_done: boolean; talk_note: string | null };

const T = {
  uz: { add: "Yangi material", title: "Nomi", desc: "Tavsif / metodika", file: "Video yoki fayl (≤ 49 MB)", or: "yoki havola (https://…)",
    save: "Saqlash", send: "Yuborish", who: "Kimga yuboriladi", talk: "Suhbat", talkAt: "Suhbat vaqti", talkWith: "Kim o'tkazadi",
    msg: "Qo'shimcha xabar", sent: "yuborilgan", talks: "suhbat", done: "o'tkazildi", markDone: "O'tkazildi", noTg: "Telegram ulanmagan",
    pick: "Material tanlang", all: "Hammasi", dept: "Bo'lim", branch: "Filial", search: "Qidirish", result: "Navbatga qo'yildi",
    without: "Telegram'siz (yuborilmadi)", history: "Kimga yuborilgan", selectAll: "Hammasini belgilash", talkHint: "suhbat belgilash uchun kalendar belgisini bosing" },
  ru: { add: "Новый материал", title: "Название", desc: "Описание / методика", file: "Видео или файл (≤ 49 МБ)", or: "или ссылка (https://…)",
    save: "Сохранить", send: "Отправить", who: "Кому отправить", talk: "Беседа", talkAt: "Время беседы", talkWith: "Кто проводит",
    msg: "Дополнительное сообщение", sent: "отправлено", talks: "бесед", done: "проведено", markDone: "Проведена", noTg: "Нет Telegram",
    pick: "Выберите материал", all: "Все", dept: "Отдел", branch: "Филиал", search: "Поиск", result: "В очереди",
    without: "Без Telegram (не отправлено)", history: "Кому отправлено", selectAll: "Выбрать всех", talkHint: "нажмите значок календаря, чтобы назначить беседу" },
};

function Audience({ pos, dep, day, onPos, onDep, onDay }: { pos: number[]; dep: number[]; day: number;
  onPos: (v: number[]) => void; onDep: (v: number[]) => void; onDay: (v: number) => void }) {
  const t = useT();
  const { dicts } = usePanel();
  const pick = (e: { target: HTMLSelectElement }) => [...e.target.selectedOptions].map((o) => Number(o.value));
  return (
    <>
      <label className="field">{t.l("Kim uchun: lavozimlar (bo'sh = hamma)", "Для кого: должности (пусто = все)", "Positions (empty = all)")}
        <select multiple size={Math.min(5, Math.max(2, dicts.positions.length))} value={pos.map(String)} onChange={(e) => onPos(pick(e))} style={{ height: "auto" }}>
          {dicts.positions.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
      <label className="field">{t.l("yoki bo'limlar", "или отделы", "or departments")}
        <select multiple size={Math.min(5, Math.max(2, dicts.departments.length))} value={dep.map(String)} onChange={(e) => onDep(pick(e))} style={{ height: "auto" }}>
          {dicts.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      <label className="field">{t.l("Nechanchi kuni yuborilsin (0 = birinchi kun)", "На какой день отправить (0 = первый)", "Day")}
        <input type="number" min={0} max={60} value={day} onChange={(e) => onDay(Math.max(0, Math.min(60, Number(e.target.value) || 0)))} /></label>
    </>
  );
}

function NewMaterial({ s, onDone }: { s: typeof T.ru; onDone: () => void }) {
  const [f, setF] = useState({ title: "", description: "", url: "" });
  const [pos, setPos] = useState<number[]>([]);
  const [dep, setDep] = useState<number[]>([]);
  const [day, setDay] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <section className="card">
      <div className="card-h"><span className="card-t">{s.add}</span><span className="card-s">mp4 · mov · pdf · docx · pptx · xlsx · link</span></div>
      <div className="stack">
        <label className="field">{s.title}<input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
        <label className="field">{s.desc}<textarea rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
        <label className="field">{s.file}<input type="file" accept=".mp4,.mov,.m4v,.webm,.pdf,.docx,.pptx,.xlsx,.txt,.md,.png,.jpg" style={{ height: "auto" }}
          onChange={(e) => setFile(e.target.files?.[0] || null)} /></label>
        <label className="field">{s.or}<input value={f.url} disabled={!!file} onChange={(e) => setF({ ...f, url: e.target.value })} /></label>
        <Audience pos={pos} dep={dep} day={day} onPos={setPos} onDep={setDep} onDay={setDay} />
        <Err e={err} />
        <button className="btn primary" disabled={busy || f.title.trim().length < 2 || (!file && !f.url.trim())} onClick={async () => {
          setBusy(true); setErr(null);
          const form = new FormData();
          form.append("title", f.title); form.append("description", f.description);
          if (file) form.append("file", file); else form.append("url", f.url.trim());
          form.append("position_ids", pos.join(",")); form.append("department_ids", dep.join(",")); form.append("day_offset", String(day));
          try { await api("/api/onboarding/materials", { form }); setF({ title: "", description: "", url: "" }); setFile(null); onDone(); }
          catch (x: any) { setErr(x.message); } finally { setBusy(false); }
        }}>{busy ? "…" : s.save}</button>
      </div>
    </section>
  );
}

function SendModal({ m, s, onClose, onDone }: { m: Mat; s: typeof T.ru; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const { dicts } = usePanel();
  const emps = useLoad<Emp[]>("/api/employees");
  const [dept, setDept] = useState("");
  const [branch, setBranch] = useState("");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [talk, setTalk] = useState<number[]>([]);
  const [talkAt, setTalkAt] = useState("");
  const [talkWith, setTalkWith] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<{ queued: number; without_telegram: string[] } | null>(null);
  const list = useMemo(() => (emps.data || []).filter((e) => e.status !== "fired"
    && (!dept || String(e.department_id) === dept) && (!branch || String(e.branch_id) === branch)
    && (!q || e.full_name.toLowerCase().includes(q.toLowerCase()))), [emps.data, dept, branch, q]);
  const toggle = (arr: number[], id: number) => (arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]);
  return (
    <Modal title={`${s.send}: ${m.title}`} onClose={onClose}>
      {res ? (
        <div className="stack">
          <div className="note">{s.result}: {res.queued}</div>
          {res.without_telegram.length > 0 && <div className="error">{s.without}: {res.without_telegram.join(", ")}</div>}
          <div className="row"><span className="spacer" /><button className="btn primary" onClick={() => { onDone(); onClose(); }}>OK</button></div>
        </div>
      ) : (
        <div className="stack">
          <div className="row">
            <select value={dept} onChange={(e) => setDept(e.target.value)} aria-label={s.dept} style={{ flex: 1 }}>
              <option value="">{s.dept}: {s.all}</option>{dicts.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
            <select value={branch} onChange={(e) => setBranch(e.target.value)} aria-label={s.branch} style={{ flex: 1 }}>
              <option value="">{s.branch}: {s.all}</option>{dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select>
            <input placeholder={s.search} value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: 1 }} />
          </div>
          <div className="row small muted"><b style={{ color: "var(--ink)" }}>{s.who}: {picked.length}</b> · {s.talk}: {talk.length} · {s.talkHint}
            <span className="spacer" /><button className="lnk" onClick={() => setPicked([...new Set([...picked, ...list.map((e) => e.id)])])}>{s.selectAll}</button></div>
          <div className="checks" style={{ maxHeight: 280, overflowY: "auto", gridTemplateColumns: "1fr" }}>
            {list.map((e) => (
              <div key={e.id} className="check" style={{ alignItems: "center" }}>
                <input type="checkbox" checked={picked.includes(e.id)} onChange={() => { setPicked(toggle(picked, e.id)); if (picked.includes(e.id)) setTalk(talk.filter((x) => x !== e.id)); }} />
                <span style={{ flex: 1 }}><b>{e.full_name}</b><span>{[e.position, e.branch, e.department].filter(Boolean).join(" · ")}{e.telegram_linked ? "" : ` · ${s.noTg}`}</span></span>
                <button type="button" className={`btn sm${talk.includes(e.id) ? " primary" : ""}`} disabled={!picked.includes(e.id)} title={s.talk}
                  onClick={() => setTalk(toggle(talk, e.id))}><CalendarDays className="ic inl" size={14} aria-hidden="true" /> {s.talk}</button>
              </div>
            ))}
            {list.length === 0 && <Empty />}
          </div>
          {talk.length > 0 && <div className="grid two">
            <label className="field">{s.talkAt}<input type="datetime-local" value={talkAt} onChange={(e) => setTalkAt(e.target.value)} /></label>
            <label className="field">{s.talkWith}<input value={talkWith} onChange={(e) => setTalkWith(e.target.value)} /></label>
          </div>}
          <label className="field">{s.msg}<textarea rows={2} maxLength={1000} value={msg} onChange={(e) => setMsg(e.target.value)} /></label>
          <Err e={err} />
          <div className="row"><span className="spacer" />
            <button className="btn" onClick={onClose}>{t("cancel")}</button>
            <button className="btn primary" disabled={!picked.length || (talk.length > 0 && (!talkAt || !talkWith.trim()))} onClick={async () => {
              try { setRes(await api("/api/onboarding/materials/" + m.id + "/send", { body: {
                employee_ids: picked, talk_employee_ids: talk, talk_at: talkAt || null, talk_with: talkWith || null, message: msg } })); }
              catch (x: any) { setErr(x.message); }
            }}><Ic n="send" />{s.send} · {picked.length}</button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function Sends({ m, s }: { m: Mat; s: typeof T.ru }) {
  const { me } = usePanel();
  const list = useLoad<Send[]>(`/api/onboarding/materials/${m.id}/sends`, [m.id, m.sent]);
  const dt = (v: string | null) => (v ? new Date(v).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—");
  return (
    <section className="card">
      <div className="card-h"><span className="card-t">{s.history}</span><span className="card-s">{m.title}</span></div>
      {list.data && list.data.length ? (
        <div className="tbl-wrap"><table className="tbl">
          <tbody>{list.data.map((x) => (
            <tr key={x.id}>
              <td>{x.full_name}<span className="sub">{x.branch}{x.telegram ? "" : ` · ${s.noTg}`}</span></td>
              <td className="small">{dt(x.sent_at)}</td>
              <td>{x.talk_at ? <span className="small"><CalendarDays className="ic inl" size={14} aria-hidden="true" /> {dt(x.talk_at)} · {x.talk_with}</span> : <span className="muted">—</span>}</td>
              <td className="r">{x.talk_at && (x.talk_done ? <span className="badge b-ok">{s.done}</span>
                : can(me, "onboarding") && <button className="btn sm" onClick={() => api(`/api/onboarding/materials/sends/${x.id}/talk-done`, { body: { note: "" } }).then(list.reload)}>{s.markDone}</button>)}</td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : <Empty />}
    </section>
  );
}

function TagsModal({ m, onClose, onDone }: { m: Mat; onClose: () => void; onDone: () => void }) {
  const t = useT();
  const [pos, setPos] = useState<number[]>(m.position_ids);
  const [dep, setDep] = useState<number[]>(m.department_ids);
  const [day, setDay] = useState(m.day_offset);
  const [forNew, setForNew] = useState(m.for_new);
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal title={m.title} onClose={onClose}>
      <div className="stack">
        <Audience pos={pos} dep={dep} day={day} onPos={setPos} onDep={setDep} onDay={setDay} />
        <label className="check"><input type="checkbox" checked={forNew} onChange={(e) => setForNew(e.target.checked)} />
          <span><b>{t.l("Yangi xodimlarga avtomatik", "Новичкам автоматически", "Auto for newcomers")}</b></span></label>
        <Err e={err} />
        <div className="row"><span className="spacer" />
          <button className="btn primary" onClick={() => api(`/api/onboarding/materials/${m.id}`, { method: "PATCH", body: {
            position_ids: pos, department_ids: dep, day_offset: day, for_new: forNew } }).then(() => { onDone(); onClose(); }).catch((x) => setErr(x.message))}>{t("save")}</button>
        </div>
      </div>
    </Modal>
  );
}

/** HR picks a person -> the agent proposes a course (rules + meaning) -> HR edits days / unticks -> start. */
function CoursePlanner() {
  const t = useT();
  const emps = useLoad<Emp[]>("/api/employees");
  const [emp, setEmp] = useState("");
  const [plan, setPlan] = useState<PlanItem[] | null>(null);
  const [on, setOn] = useState<Record<number, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const prog = useLoad<Progress>(emp ? `/api/onboarding/materials/employee/${emp}` : null, [emp, msg]);
  const fmt = (v: string | null) => (v ? v.slice(5, 16).replace("T", " ") : "—");
  return (
    <section className="card">
      <div className="card-h"><span className="card-t"><Ic n="spark" /> {t.l("Xodim uchun onboarding kursi", "Курс онбординга для сотрудника", "Onboarding course")}</span>
        <span className="card-s">{t.l("Agent lavozim va ishga qarab video/instruksiyalarni tanlaydi", "Агент подбирает видео и инструкции по должности и работе", "")}</span></div>
      <div className="row">
        <select value={emp} onChange={(e) => { setEmp(e.target.value); setPlan(null); setMsg(null); }} style={{ flex: 1 }}>
          <option value="">{t.l("Xodimni tanlang", "Выберите сотрудника", "Employee")}</option>
          {(emps.data || []).filter((e) => e.status !== "fired").map((e) => <option key={e.id} value={e.id}>{e.full_name} · {e.position || "—"}</option>)}
        </select>
        <button className="btn primary" disabled={!emp || busy} onClick={async () => {
          setBusy(true); setErr(null); setMsg(null);
          try {
            const r = await api<{ items: PlanItem[] }>(`/api/onboarding/materials/course/${emp}`);
            setPlan(r.items); setOn(Object.fromEntries(r.items.map((x) => [x.material_id, true])));
          } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
        }}>{busy ? t.l("Agent tanlayapti…", "Агент подбирает…", "…") : t.l("Agent tanlasin", "Подобрать агентом", "Pick")}</button>
      </div>
      <Err e={err} />
      {plan && (plan.length === 0 ? <div className="empty">{t.l("Mos material yo'q yoki hammasi yuborilgan", "Подходящих нет или всё отправлено", "Nothing to add")}</div> : (
        <div className="stack" style={{ marginTop: 10 }}>
          {plan.map((x, i) => (
            <label key={x.material_id} className="check" style={{ alignItems: "center" }}>
              <input type="checkbox" checked={!!on[x.material_id]} onChange={(e) => setOn({ ...on, [x.material_id]: e.target.checked })} />
              <span style={{ flex: 1 }}><b>{x.title}</b><span>{x.reason} · {x.source === "ai" ? "AI" : x.source === "rule+ai" ? t.l("qoida + AI", "правило + ИИ", "rule+AI") : t.l("qoida", "правило", "rule")}</span></span>
              <span className="small muted">{t.l("kun", "день", "day")}</span>
              <input type="number" min={0} max={60} value={x.day} style={{ width: 64 }}
                onChange={(e) => setPlan(plan.map((p, j) => (j === i ? { ...p, day: Math.max(0, Math.min(60, Number(e.target.value) || 0)) } : p)))} />
            </label>
          ))}
          <div className="row"><span className="spacer" />
            <button className="btn primary" disabled={!plan.some((x) => on[x.material_id])} onClick={async () => {
              try {
                const r = await api<{ scheduled: number; sent_now: number }>(`/api/onboarding/materials/course/${emp}`,
                  { body: { items: plan.filter((x) => on[x.material_id]) } });
                setPlan(null);
                setMsg(t.l(`Rejalashtirildi: ${r.scheduled}, hozir yuborildi: ${r.sent_now}`, `Запланировано: ${r.scheduled}, отправлено сейчас: ${r.sent_now}`, ""));
              } catch (x: any) { setErr(x.message); }
            }}><Ic n="send" />{t.l("Kursni boshlash", "Запустить курс", "Start")}</button>
          </div>
        </div>
      ))}
      {msg && <div className="note" style={{ marginTop: 10 }}>{msg}</div>}
      {prog.data && prog.data.items.length > 0 && (
        <div className="tbl-wrap" style={{ marginTop: 12 }}><table className="tbl">
          <thead><tr><th>{t.l("Material", "Материал", "Material")}</th><th>{t.l("Reja", "План", "Plan")}</th><th>{t.l("Yuborildi", "Отправлено", "Sent")}</th><th>{t.l("Ko'rdi", "Посмотрел", "Viewed")}</th></tr></thead>
          <tbody>{prog.data.items.map((x) => (
            <tr key={x.id}><td>{x.title}{x.reason && <span className="sub">{x.reason}</span>}</td><td className="small">{x.scheduled_for || "—"}</td>
              <td className="small">{fmt(x.sent_at)}</td><td>{x.viewed_at ? <span className="badge b-ok"><Check className="ic inl" size={14} aria-hidden="true" /> {fmt(x.viewed_at)}</span> : <span className="muted">—</span>}</td></tr>
          ))}</tbody>
        </table>{!prog.data.telegram && <div className="error small" style={{ marginTop: 8 }}>{t.l("Telegram ulanmagan — yuborilmaydi", "Telegram не привязан — не отправится", "")}</div>}</div>
      )}
    </section>
  );
}


export default function Materials() {
  const { lang } = useContext(LangCtx);
  const s = lang === "uz" ? T.uz : T.ru;
  const { me } = usePanel();
  const mats = useLoad<Mat[]>("/api/onboarding/materials");
  const [sel, setSel] = useState<Mat | null>(null);
  const [sendFor, setSendFor] = useState<Mat | null>(null);
  const [tags, setTags] = useState<Mat | null>(null);
  const { dicts } = usePanel();
  const aud = (m: Mat) => [...m.position_ids.map((i) => dicts.positions.find((p) => p.id === i)?.title),
    ...m.department_ids.map((i) => dicts.departments.find((d) => d.id === i)?.name)].filter(Boolean).join(", ");
  const write = can(me, "onboarding");
  const icon = (k: string) => (k === "video" ? <Play className="ic inl" size={14} aria-hidden="true" /> : k === "link" ? <Link className="ic inl" size={14} aria-hidden="true" /> : <FileText className="ic inl" size={14} aria-hidden="true" />);
  return (
    <div className="grid">
      {write && <div className="span-4"><NewMaterial s={s} onDone={mats.reload} /></div>}
      <div className={`${write ? "span-8" : "span-12"} stack`}>
        <Err e={mats.error} />
        <section className="card">
          <div className="card-h"><span className="card-t">{lang === "uz" ? "Onboarding materiallari" : "Материалы онбординга"}</span>
            <span className="card-s">{mats.data?.length ?? 0}</span></div>
          {mats.data && mats.data.length ? (
            <div className="tbl-wrap"><table className="tbl">
              <tbody>{mats.data.map((m) => (
                <tr key={m.id} className={sel?.id === m.id ? "sel" : ""} style={{ cursor: "pointer" }} onClick={() => setSel(m)}>
                  <td><span className="named"><span className="avatar">{icon(m.kind)}</span>
                    <span><b style={{ fontWeight: 600 }}>{m.title}</b><span className="sub">{aud(m) || (lang === "uz" ? "hamma uchun" : "для всех")} · {lang === "uz" ? "kun" : "день"} {m.day_offset}</span></span></span></td>
                  <td className="r small">{m.sent} {s.sent} · {m.viewed} <Check className="ic inl" size={14} aria-hidden="true" /><span className="sub">{m.planned} {lang === "uz" ? "rejada" : "в плане"}</span></td>
                  <td className="r"><div className="row" style={{ justifyContent: "flex-end" }} onClick={(e) => e.stopPropagation()}>
                    {m.filename && <button className="btn sm" onClick={() => download(`/api/onboarding/materials/${m.id}/file`, m.filename!)}>↓</button>}
                    {m.url && <a className="btn sm" href={m.url} target="_blank" rel="noopener noreferrer" aria-label="Open"><ExternalLink className="ic inl" size={14} aria-hidden="true" /></a>}
                    {write && <button className="btn sm" onClick={() => setTags(m)}>{lang === "uz" ? "Kim uchun" : "Для кого"}</button>}
                    {write && <button className="btn sm primary" onClick={() => setSendFor(m)}><Ic n="send" />{s.send}</button>}
                  </div></td>
                </tr>
              ))}</tbody>
            </table></div>
          ) : <Empty />}
        </section>
        {write && <CoursePlanner />}
        {sel ? <Sends m={mats.data?.find((x) => x.id === sel.id) || sel} s={s} /> : null}
      </div>
      {sendFor && <SendModal m={sendFor} s={s} onClose={() => setSendFor(null)} onDone={mats.reload} />}
      {tags && <TagsModal m={tags} onClose={() => setTags(null)} onDone={mats.reload} />}
    </div>
  );
}
