import { useEffect, useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import { Ic } from "../icons";
import { Err, Modal } from "../ui";
import { usePanel } from "./ctx";

export type Vac = {
  id: number; title: string; branch_id: number | null; branch: string | null; status: string; salary_text: string | null;
  schedule_text: string | null; intro: string | null; duties: string | null; requirements: string | null; benefits: string | null;
  ad_text: string | null; public: boolean; is_template: boolean; published: Record<string, string>; missing: string[];
  apply_url: string | null; channel_configured: boolean;
  revisions?: { id: number; comment: string | null; author: string; created_at: string }[];
};

const FIELDS = ["title", "salary_text", "schedule_text", "intro", "duties", "requirements", "benefits"] as const;

/** Brief -> agent draft. */
export function NewVacancy({ onClose, onOpen }: { onClose: () => void; onOpen: (v: Vac) => void }) {
  const t = useT();
  const { dicts } = usePanel();
  const [brief, setBrief] = useState("");
  const [branch, setBranch] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal title={t.l("Agent bilan vakansiya", "Вакансия с агентом", "Vacancy with the agent")} onClose={onClose}>
      <div className="stack">
        <label className="field">{t.l("Kim kerak? Erkin yozing", "Кто нужен? Пишите свободно", "Who do you need?")}
          <textarea rows={5} value={brief} onChange={(e) => setBrief(e.target.value)}
            placeholder={t.l("Masalan: ofisga buxgalter kerak, 6/1, 09:00–18:00, maosh 7 mln, 1C bilishi shart",
              "Например: нужен бухгалтер в офис, 6/1, 09:00–18:00, оклад 7 млн, знание 1С", "e.g. accountant for the office…")} /></label>
        <label className="field">{t("c_branch")}
          <select value={branch} onChange={(e) => setBranch(e.target.value)}>
            <option value="">{t.l("Agent o'zi aniqlasin", "Агент определит сам", "Let the agent decide")}</option>
            {dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select></label>
        <div className="note small">{t.l("Agent maosh, telefon va havolalarni o'ylab topmaydi — faqat siz yozganini oladi.",
          "Агент не выдумывает зарплату, телефоны и ссылки — берёт только то, что вы написали.", "The agent never invents salary or contacts.")}</div>
        <Err e={err} />
        <div className="row"><span className="spacer" />
          <button className="btn" onClick={onClose}>{t("cancel")}</button>
          <button className="btn primary" disabled={busy || brief.trim().length < 3} onClick={async () => {
            setBusy(true); setErr(null);
            try { onOpen(await api<Vac>("/api/vacancies/ai", { body: { brief, branch_id: branch ? Number(branch) : null } })); }
            catch (x: any) { setErr(x.message); } finally { setBusy(false); }
          }}><Ic n="spark" />{busy ? t.l("Yozyapman…", "Пишу…", "Writing…") : t.l("Agent yozsin", "Написать агентом", "Write")}</button>
        </div>
      </div>
    </Modal>
  );
}

/** Edit fields by hand or ask the agent to rewrite; versions; publish once per platform. */
export function VacancyEditor({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged: () => void }) {
  const t = useT();
  const { dicts } = usePanel();
  const [v, setV] = useState<Vac | null>(null);
  const [f, setF] = useState<Record<string, string>>({});
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [web, setWeb] = useState(true);
  const [channel, setChannel] = useState(false);
  const load = (x: Vac) => {
    setV(x);
    setF(Object.fromEntries([...FIELDS.map((k) => [k, (x as any)[k] || ""]), ["branch_id", x.branch_id ? String(x.branch_id) : ""]]));
  };
  useEffect(() => { api<Vac>(`/api/vacancies/${id}`).then(load).catch((x) => setErr(x.message)); }, [id]);
  const run = async (key: string, p: Promise<Vac>) => {
    setBusy(key); setErr(null);
    try { load(await p); onChanged(); } catch (x: any) { setErr(x.message); } finally { setBusy(null); }
  };
  if (!v) return <Modal title="…" onClose={onClose}><Err e={err} /></Modal>;
  const dirty = FIELDS.some((k) => (f[k] || "") !== ((v as any)[k] || "")) || (f.branch_id || "") !== (v.branch_id ? String(v.branch_id) : "");
  const label: Record<string, string> = {
    title: t.l("Lavozim", "Должность", "Position"), salary_text: t.l("Maosh (aynan qanday yozilsa)", "Зарплата (как есть)", "Salary"),
    schedule_text: t.l("Ish vaqti", "График", "Schedule"), intro: t.l("Kirish matni", "Вступление", "Intro"),
    duties: t.l("Vazifalar (har biri yangi qatorda)", "Обязанности (по строке)", "Duties"),
    requirements: t.l("Talablar (har biri yangi qatorda)", "Требования (по строке)", "Requirements"),
    benefits: t.l("Biz taklif qilamiz", "Мы предлагаем", "We offer"),
  };
  const missName: Record<string, string> = { branch: t("c_branch"), salary_text: label.salary_text, schedule_text: label.schedule_text, title: label.title };
  return (
    <Modal title={`#${v.id} · ${v.title}`} onClose={onClose}>
      <div className="vac-ed">
        <div className="stack">
          <label className="field">{label.title}<input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
          <label className="field">{t("c_branch")}<select value={f.branch_id} onChange={(e) => setF({ ...f, branch_id: e.target.value })}>
            <option value="">—</option>{dicts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
          <div className="grid two" style={{ gap: 8 }}>
            <label className="field">{label.salary_text}<input value={f.salary_text} onChange={(e) => setF({ ...f, salary_text: e.target.value })} /></label>
            <label className="field">{label.schedule_text}<input value={f.schedule_text} onChange={(e) => setF({ ...f, schedule_text: e.target.value })} /></label>
          </div>
          {(["intro", "duties", "requirements", "benefits"] as const).map((k) => (
            <label key={k} className="field">{label[k]}<textarea rows={k === "intro" ? 2 : 4} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></label>
          ))}
          <button className="btn primary" disabled={!dirty || !!busy} onClick={() => run("save", api<Vac>(`/api/vacancies/${v.id}`, { method: "PATCH", body: {
            ...Object.fromEntries(FIELDS.map((k) => [k, f[k]])), branch_id: f.branch_id ? Number(f.branch_id) : null } }))}>{t("save")}</button>
        </div>
        <div className="stack">
          <div className="row"><span className={`badge ${v.status === "open" ? "b-ok" : ""}`}>{v.status}</span>
            {v.public && <span className="badge b-info">{t.l("saytda", "на сайте", "on site")}</span>}
            {v.is_template && <span className="badge">{t.l("shablon", "шаблон", "template")}</span>}
            {Object.keys(v.published).map((p) => <span key={p} className="badge b-ok">✓ {p}</span>)}</div>
          {v.missing.length > 0 && <div className="error small">{t.l("E'lon uchun to'ldiring", "Для публикации заполните", "Fill in")}: {v.missing.map((m) => missName[m] || m).join(", ")}</div>}
          <pre className="ad-preview">{v.ad_text}</pre>
          <div className="card" style={{ padding: 12, boxShadow: "none" }}>
            <label className="field"><span><Ic n="spark" /> {t.l("Agentga izoh — u qayta yozadi", "Комментарий агенту — он перепишет", "Ask the agent to rewrite")}</span>
              <textarea rows={2} value={comment} onChange={(e) => setComment(e.target.value)}
                placeholder={t.l("masalan: qisqaroq, maosh 6 mln, 1C talab qil", "например: короче, оклад 6 млн, нужен 1С", "e.g. shorter")} /></label>
            <button className="btn" style={{ marginTop: 8 }} disabled={comment.trim().length < 2 || !!busy}
              onClick={() => run("rw", api<Vac>(`/api/vacancies/${v.id}/rewrite`, { body: { comment } })).then(() => setComment(""))}>
              {busy === "rw" ? t.l("Yozyapman…", "Пишу…", "Writing…") : t.l("Agent qayta yozsin", "Переписать агентом", "Rewrite")}</button>
          </div>
          {v.status !== "closed" && <div className="card" style={{ padding: 12, boxShadow: "none" }}>
            <div className="row small">
              <label className="row"><input type="checkbox" checked disabled /> {t.l("Botda", "В боте", "Bot")}</label>
              <label className="row"><input type="checkbox" checked={web} onChange={(e) => setWeb(e.target.checked)} /> {t.l("Saytda (/jobs)", "На сайте (/jobs)", "Site")}</label>
              <label className="row" title={v.channel_configured ? "" : "recruiting.jobs_channel"}>
                <input type="checkbox" checked={channel} disabled={!v.channel_configured || "channel" in v.published} onChange={(e) => setChannel(e.target.checked)} />
                {t.l("Telegram kanal", "Telegram-канал", "Channel")}{!v.channel_configured && " —"}</label>
            </div>
            <button className="btn primary" style={{ marginTop: 8 }} disabled={!!busy || v.missing.length > 0 || dirty}
              onClick={() => run("pub", api<Vac>(`/api/vacancies/${v.id}/publish`, { body: { web, channel } }))}>
              ✅ {v.status === "open" ? t.l("Yangilab e'lon qilish", "Опубликовать ещё", "Publish more") : t.l("E'lon qilish", "Опубликовать", "Publish")}</button>
            {dirty && <div className="small muted" style={{ marginTop: 6 }}>{t.l("Avval saqlang", "Сначала сохраните", "Save first")}</div>}
          </div>}
          <div className="row">
            <button className="btn sm" onClick={() => run("dup", api<Vac>(`/api/vacancies/${v.id}/duplicate`, { method: "POST" }))}>{t.l("Nusxa olish", "Копия", "Duplicate")}</button>
            <button className="btn sm" onClick={() => run("tpl", api<Vac>(`/api/vacancies/${v.id}/template`, { body: { is_template: !v.is_template } }))}>
              {v.is_template ? t.l("Shablondan olish", "Убрать из шаблонов", "Untemplate") : t.l("Shablonga saqlash", "В шаблоны", "Save as template")}</button>
            {v.status !== "closed" && <button className="btn sm danger" onClick={() => run("close", api<Vac>(`/api/vacancies/${v.id}/close`, { method: "POST" }))}>{t.l("Yopish", "Закрыть", "Close")}</button>}
            {v.apply_url && v.status === "open" && <a className="btn sm" href={v.apply_url} target="_blank" rel="noopener noreferrer">↗ {t.l("Bot havolasi", "Ссылка бота", "Bot link")}</a>}
          </div>
          <Err e={err} />
          {v.revisions && v.revisions.length > 0 && <details className="small">
            <summary>{t.l("Versiyalar", "Версии", "Versions")} · {v.revisions.length}</summary>
            {v.revisions.map((r) => (
              <div key={r.id} className="row" style={{ padding: "4px 0", borderBottom: "1px solid var(--grid)" }}>
                <span className="muted">{r.created_at.slice(5, 16).replace("T", " ")}</span><span>{r.comment}</span><span className="spacer" />
                <button className="lnk" onClick={() => run("rev", api<Vac>(`/api/vacancies/${v.id}/revert/${r.id}`, { method: "POST" }))}>{t.l("qaytarish", "вернуть", "revert")}</button>
              </div>
            ))}
          </details>}
        </div>
      </div>
    </Modal>
  );
}
