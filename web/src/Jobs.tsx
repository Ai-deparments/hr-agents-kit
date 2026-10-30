import { useEffect, useState } from "react";
import { api } from "./api";

type Job = { id: number; title: string; city: string | null; schedule: string | null; salary: string | null; text: string | null;
  apply_url: string | null; opened_at: string | null };

/** Public vacancies page (no login): /jobs, /jobs#12 opens one vacancy. Apply = Telegram bot interview. */
export default function Jobs() {
  const [data, setData] = useState<{ company: string; jobs: Job[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(() => Number(location.hash.slice(1)) || null);
  useEffect(() => { api<{ company: string; jobs: Job[] }>("/api/public/jobs").then(setData).catch((e) => setErr(e.message)); }, []);
  useEffect(() => {
    const on = () => setOpen(Number(location.hash.slice(1)) || null);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  useEffect(() => { if (data) document.title = `${data.company} · Vakansiyalar`; }, [data]);
  const job = data?.jobs.find((j) => j.id === open);
  return (
    <div className="jobs">
      <header className="jobs-hdr">
        <span className="logo">{data?.company || ""}</span>
        <h1>Vakansiyalar · Вакансии</h1>
        <p className="muted">Ariza Telegram bot orqali 5 daqiqada · Заявка через Telegram-бота за 5 минут</p>
      </header>
      {err && <div className="error">{err}</div>}
      {data && data.jobs.length === 0 && <div className="empty">Hozircha ochiq vakansiya yo'q · Сейчас открытых вакансий нет</div>}
      {job ? (
        <article className="card job-full">
          <a className="lnk" href="#" onClick={(e) => { e.preventDefault(); location.hash = ""; }}>← Barcha vakansiyalar · Все вакансии</a>
          <pre className="ad-preview">{job.text}</pre>
          {job.apply_url && <a className="btn primary big" href={job.apply_url} target="_blank" rel="noopener noreferrer">✍️ Ariza topshirish · Откликнуться</a>}
        </article>
      ) : (
        <div className="jobs-list">
          {data?.jobs.map((j) => (
            <a key={j.id} className="card job" href={`#${j.id}`}>
              <b>{j.title}</b>
              <span className="muted">{[j.city, j.schedule].filter(Boolean).join(" · ")}</span>
              <span className="job-salary">{j.salary || "Maosh suhbatda · ЗП на собеседовании"}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
