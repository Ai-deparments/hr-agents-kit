import { Check, ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import { Ic } from "../icons";
import { Err, Modal, useLoad } from "../ui";
import { usePanel } from "./ctx";

export type Vac = {
  id: number; title: string; branch_id: number | null; branch: string | null; status: string; salary_text: string | null;
  schedule_text: string | null; intro: string | null; duties: string | null; requirements: string | null; benefits: string | null;
  ad_text: string | null; public: boolean; is_template: boolean; published: Record<string, string>; missing: string[];
  apply_url: string | null; channel_configured: boolean; ad_custom: boolean;
  variants: { n: number; text: string; source: string; chosen: boolean }[];
  jobs: { id: number; status: string; instruction: string; result: string | null; problems: string[]; error: string | null; created_at: string }[];
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
            {Object.keys(v.published).map((p) => <span key={p} className="badge b-ok"><Check className="ic inl" size={14} aria-hidden="true" /> {p}</span>)}</div>
          {v.missing.length > 0 && <div className="error small">{t.l("E'lon uchun to'ldiring", "Для публикации заполните", "Fill in")}: {v.missing.map((m) => missName[m] || m).join(", ")}</div>}
          <pre className="ad-preview">{v.ad_text}</pre>
          <AdStudio v={v} busy={busy} run={run} dirty={dirty} />
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
              <Check className="ic inl" size={14} aria-hidden="true" /> {v.status === "open" ? t.l("Yangilab e'lon qilish", "Опубликовать ещё", "Publish more") : t.l("E'lon qilish", "Опубликовать", "Publish")}</button>
            {dirty && <div className="small muted" style={{ marginTop: 6 }}>{t.l("Avval saqlang", "Сначала сохраните", "Save first")}</div>}
          </div>}
          <div className="row">
            <button className="btn sm" onClick={() => run("dup", api<Vac>(`/api/vacancies/${v.id}/duplicate`, { method: "POST" }))}>{t.l("Nusxa olish", "Копия", "Duplicate")}</button>
            <button className="btn sm" onClick={() => run("tpl", api<Vac>(`/api/vacancies/${v.id}/template`, { body: { is_template: !v.is_template } }))}>
              {v.is_template ? t.l("Shablondan olish", "Убрать из шаблонов", "Untemplate") : t.l("Shablonga saqlash", "В шаблоны", "Save as template")}</button>
            {v.status !== "closed" && <button className="btn sm danger" onClick={() => run("close", api<Vac>(`/api/vacancies/${v.id}/close`, { method: "POST" }))}>{t.l("Yopish", "Закрыть", "Close")}</button>}
            {v.apply_url && v.status === "open" && <a className="btn sm" href={v.apply_url} target="_blank" rel="noopener noreferrer"><ExternalLink className="ic inl" size={14} aria-hidden="true" /> {t.l("Bot havolasi", "Ссылка бота", "Bot link")}</a>}
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

/** 2 variants from the agent, a checked manual edit and "a task for the agent" — a person always applies the text. */
function AdStudio({ v, busy, run, dirty }: { v: Vac; busy: string | null; run: (k: string, p: Promise<Vac>) => Promise<void>; dirty: boolean }) {
  const t = useT();
  const [text, setText] = useState<string | null>(null);
  const [chk, setChk] = useState<any | null>(null);
  const [task, setTask] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const JOB: Record<string, string> = { queued: t.l("navbatda", "в очереди", "queued"), running: t.l("ishlayapti", "в работе", "running"),
    done: t.l("tayyor", "готово", "done"), failed: t.l("xato", "ошибка", "failed"), applied: t.l("qo'llandi", "применено", "applied") };
  return (
    <div className="card stack" style={{ padding: 12, boxShadow: "none" }}>
      <div className="row"><b>{t.l("E'lon matni", "Текст объявления", "Ad text")}</b>
        <span className="badge">{v.ad_custom ? t.l("tanlangan matn", "выбранный текст", "chosen text") : t.l("shablon", "шаблон", "template")}</span><span className="spacer" />
        <button className="btn sm" disabled={!!busy || dirty || v.missing.length > 0} onClick={() => run("var", api<Vac>(`/api/vacancies/${v.id}/variants`, { method: "POST" }))}>
          <Ic n="spark" />{busy === "var" ? t.l("Yozyapman…", "Пишу…", "Writing…") : t.l("2 ta variant", "2 варианта", "2 variants")}</button>
        {v.ad_custom && <button className="btn sm" disabled={!!busy} onClick={() => run("tplad", api<Vac>(`/api/vacancies/${v.id}/ad/template`, { method: "POST" }))}>
          {t.l("Shablonga qaytish", "Вернуть шаблон", "Back to template")}</button>}
      </div>
      {v.variants.map((a) => (
        <div key={a.n} className="stack" style={{ gap: 4 }}>
          <div className="row small"><b>{a.n}-variant</b><span className="muted">{a.source === "agent" ? t.l("agent", "агент", "agent") : t.l("shablon", "шаблон", "template")}</span>
            <span className="spacer" />{a.chosen ? <span className="badge b-ok">✓</span> :
              <button className="btn sm" disabled={!!busy} onClick={() => run("pick", api<Vac>(`/api/vacancies/${v.id}/variants/${a.n}/choose`, { method: "POST" }))}>{t.l("Tanlash", "Выбрать", "Choose")}</button>}</div>
          <pre className="ad-preview" style={{ maxHeight: 160 }}>{a.text}</pre>
        </div>
      ))}
      {text === null ? <button className="btn sm" onClick={() => { setText(v.ad_text || ""); setChk(null); }}>{t.l("Matnni qo'lda tahrirlash", "Править текст вручную", "Edit the text")}</button> : <>
        <textarea rows={8} value={text} onChange={(e) => { setText(e.target.value); setChk(null); }} />
        {chk && <div className={chk.ok ? "note small" : "error small"}>{chk.ok ? t.l("Tekshiruvdan o'tdi", "Проверка пройдена", "Passed the check") : chk.problems.join("; ")}
          {chk.removed.length > 0 && <div>{t.l("Olib tashlanadi", "Будет удалено", "Will be cut")}: {chk.removed.join(", ")}</div>}</div>}
        <div className="row">
          <button className="btn sm" onClick={async () => { try { setChk(await api(`/api/vacancies/${v.id}/ad/check`, { body: { text } })); } catch (x: any) { setErr(x.message); } }}>
            {t.l("Tekshirish", "Проверить", "Check")}</button>
          <button className="btn sm primary" disabled={!!busy} onClick={() => run("ad", api<Vac>(`/api/vacancies/${v.id}/ad`, { method: "PATCH", body: { text } })).then(() => setText(null))}>{t("save")}</button>
          <button className="btn sm" onClick={() => setText(null)}>{t("cancel")}</button></div>
      </>}
      <label className="field"><span><Ic n="spark" /> {t.l("Agentga topshiriq (natijani siz qo'llaysiz)", "Задача агенту (результат применяете вы)", "Task for the agent (you apply the result)")}</span>
        <textarea rows={2} value={task} onChange={(e) => setTask(e.target.value)} placeholder={t.l("masalan: qisqaroq, ish vaqtini boshiga", "например: короче, график в начало", "e.g. shorter, schedule first")} /></label>
      <button className="btn sm" disabled={task.trim().length < 3 || !!busy} onClick={() => run("job", api<Vac>(`/api/vacancies/${v.id}/jobs`, { body: { instruction: task } })).then(() => setTask(""))}>
        {t.l("Navbatga qo'yish", "Поставить в очередь", "Queue")}</button>
      {v.jobs.map((j) => (
        <div key={j.id} className="stack small" style={{ gap: 4, borderTop: "1px solid var(--grid)", paddingTop: 6 }}>
          <div className="row"><span className={`badge ${j.status === "done" ? "b-ok" : j.status === "failed" ? "b-bad" : ""}`}>{JOB[j.status] || j.status}</span>
            <span>{j.instruction}</span><span className="spacer" />
            {j.status === "done" && <button className="btn sm primary" disabled={!!busy} onClick={() => run("apply", api<Vac>(`/api/vacancies/jobs/${j.id}/apply`, { method: "POST" }))}>{t.l("Qo'llash", "Применить", "Apply")}</button>}</div>
          {j.result && j.status === "done" && <pre className="ad-preview" style={{ maxHeight: 140 }}>{j.result}</pre>}
          {j.problems.length > 0 && <div className="error">{j.problems.join("; ")}</div>}
          {j.error && <div className="muted">{j.error}</div>}
        </div>
      ))}
      <Err e={err} />
    </div>
  );
}

/** Admin-approved company facts: the only company facts the agent may put into an ad. */
export function CompanyFacts() {
  const t = useT();
  const f = useLoad<any>("/api/company-facts");
  const [text, setText] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!f.data) return <Err e={f.error} />;
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 8 }}><h2 style={{ margin: 0 }}>{t.l("Kompaniya faktlari", "Факты о компании", "Company facts")}</h2><span className="spacer" />
        {f.data.can_edit && text === null && <button className="btn sm" onClick={() => setText(f.data.text || "")}>{t.l("Tahrirlash", "Изменить", "Edit")}</button>}</div>
      <div className="muted small" style={{ marginBottom: 6 }}>{t.l("Agent e'lonlarda faqat shu faktlar va vakansiya kartasidagi ma'lumotlardan foydalanadi.",
        "Агент пишет объявления только из этих фактов и карточки вакансии.", "The agent uses only these facts and the vacancy card in ads.")}</div>
      {text === null ? <pre className="ad-preview" style={{ maxHeight: 180 }}>{f.data.text || "—"}</pre> : <>
        <textarea rows={6} maxLength={4000} value={text} onChange={(e) => setText(e.target.value)} />
        <div className="row" style={{ marginTop: 6 }}>
          <button className="btn sm primary" onClick={async () => {
            try { f.setData(await api("/api/company-facts", { method: "PATCH", body: { text } })); setText(null); } catch (x: any) { setErr(x.message); }
          }}>{t("save")}</button>
          <button className="btn sm" onClick={() => setText(null)}>{t("cancel")}</button></div>
      </>}
      <Err e={err} />
    </div>
  );
}
