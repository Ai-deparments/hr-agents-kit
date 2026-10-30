import { useContext, useState } from "react";
import { api } from "../api";
import { LangCtx } from "../i18n";
import { Ic } from "../icons";
import { Empty, Err, useLoad } from "../ui";

type Item = { id: string; title: string; age: number | null; area: string | null; salary: number | null; currency: string | null;
  experience_months: number | null; last_company: string | null; last_position: string | null; updated: string;
  url: string | null; name: string | null; taken: boolean };
type Res = { found: number; items: Item[]; mode: string };
type Vac = { id: number; title: string; branch: string | null; status: string };

const T = {
  uz: { q: "Kimni qidiryapsiz? (masalan: farmatsevt, провизор)", find: "hh.uz'dan qidirish", area: "Hudud", exp: "Tajriba", any: "Har qanday",
    salary: "Maosh gacha, so'm", vac: "Vakansiyaga", none: "Vakansiyasiz", take: "Nomzodlarga olish", taken: "Olingan", found: "topildi",
    years: "yil", months: "oy", open: "hh'da ochish", demo: "DEMO rejim: namunaviy rezyumelar. hh ulanganda haqiqiy baza chiqadi.",
    note: "Kontaktlar pulli — ularni HR hh.uz'da o'zi ochadi.", noexp: "Tajribasiz", e13: "1–3 yil", e36: "3–6 yil", e6: "6+ yil", age: "yosh" },
  ru: { q: "Кого ищете? (например: фармацевт, провизор)", find: "Искать на hh.uz", area: "Регион", exp: "Опыт", any: "Любой",
    salary: "Зарплата до, сум", vac: "В вакансию", none: "Без вакансии", take: "В кандидаты", taken: "Добавлен", found: "найдено",
    years: "г.", months: "мес.", open: "Открыть на hh", demo: "ДЕМО-режим: пример резюме. После подключения hh будет реальная база.",
    note: "Контакты платные — HR открывает их сам на hh.uz.", noexp: "Без опыта", e13: "1–3 года", e36: "3–6 лет", e6: "6+ лет", age: "лет" },
};

export default function HhSearch() {
  const { lang } = useContext(LangCtx);
  const s = lang === "uz" ? T.uz : T.ru;
  const status = useLoad<{ mode: string; ok: boolean; detail: string }>("/api/hh/status");
  const vacs = useLoad<Vac[]>("/api/vacancies");
  const [f, setF] = useState({ text: "", area: "uz", experience: "", salary_to: "" });
  const [vac, setVac] = useState("");
  const [res, setRes] = useState<Res | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const exp = (m: number | null) => (m === null ? "—" : m >= 12 ? `${Math.floor(m / 12)} ${s.years} ${m % 12 ? `${m % 12} ${s.months}` : ""}` : `${m} ${s.months}`);
  const run = async () => {
    setBusy(true); setErr(null);
    const q = new URLSearchParams({ text: f.text, area: f.area, ...(f.experience ? { experience: f.experience } : {}),
      ...(f.salary_to ? { salary_to: f.salary_to } : {}) });
    try { setRes(await api<Res>(`/api/hh/search?${q}`)); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  const take = async (it: Item) => {
    try {
      await api("/api/hh/take", { body: { hh_id: it.id, title: it.title, name: it.name, url: it.url, vacancy_id: vac ? Number(vac) : null,
        note: [it.last_position, it.last_company, it.area].filter(Boolean).join(", ") } });
      setRes((r) => r && { ...r, items: r.items.map((x) => (x.id === it.id ? { ...x, taken: true } : x)) });
    } catch (x: any) { setErr(x.message); }
  };
  return (
    <>
      <section className="card">
        <div className="card-h"><span className="card-t">HeadHunter · hh.uz</span>
          <span className="card-s">{status.data?.detail} · {s.note}</span>
          <span className="card-a"><span className={`badge ${status.data?.ok ? "b-ok" : "b-warn"}`}>{status.data?.mode || "…"}</span></span></div>
        {status.data?.mode === "demo" && <div className="note" style={{ marginBottom: 12 }}>{s.demo}</div>}
        <form className="row" style={{ alignItems: "flex-end" }} onSubmit={(e) => { e.preventDefault(); run(); }}>
          <label className="field" style={{ flex: "2 1 260px" }}>{s.q}<input value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} required maxLength={200} /></label>
          <label className="field" style={{ flex: "1 1 140px" }}>{s.area}<select value={f.area} onChange={(e) => setF({ ...f, area: e.target.value })}>
            <option value="uz">O'zbekiston</option><option value="tashkent">Toshkent</option><option value="samarkand">Samarqand</option>
            <option value="bukhara">Buxoro</option><option value="andijan">Andijon</option><option value="fergana">Farg'ona</option><option value="namangan">Namangan</option>
          </select></label>
          <label className="field" style={{ flex: "1 1 140px" }}>{s.exp}<select value={f.experience} onChange={(e) => setF({ ...f, experience: e.target.value })}>
            <option value="">{s.any}</option><option value="noExperience">{s.noexp}</option><option value="between1And3">{s.e13}</option>
            <option value="between3And6">{s.e36}</option><option value="moreThan6">{s.e6}</option></select></label>
          <label className="field" style={{ flex: "1 1 140px" }}>{s.salary}<input inputMode="numeric" value={f.salary_to} onChange={(e) => setF({ ...f, salary_to: e.target.value.replace(/\D/g, "") })} /></label>
          <label className="field" style={{ flex: "1 1 180px" }}>{s.vac}<select value={vac} onChange={(e) => setVac(e.target.value)}>
            <option value="">{s.none}</option>{(vacs.data || []).filter((v) => v.status === "open").map((v) => <option key={v.id} value={v.id}>{v.title} · {v.branch}</option>)}</select></label>
          <button className="btn primary" disabled={busy || !f.text.trim()} style={{ height: 34 }}><Ic n="search" />{s.find}</button>
        </form>
        <Err e={err} />
      </section>
      {res && (
        <section className="card">
          <div className="card-h"><span className="card-t">{res.found} {s.found}</span></div>
          {res.items.length === 0 ? <Empty /> : (
            <div className="tbl-wrap"><table className="tbl">
              <tbody>{res.items.map((it) => (
                <tr key={it.id}>
                  <td><span className="named"><span className="avatar">{it.title.slice(0, 2).toUpperCase()}</span>
                    <span><b style={{ fontWeight: 600 }}>{it.name || it.title}</b>
                      <span className="sub">{it.name ? `${it.title} · ` : ""}{[it.last_position, it.last_company].filter(Boolean).join(" · ") || "—"}</span></span></span></td>
                  <td className="ph-hide">{it.area || "—"}{it.age ? ` · ${it.age} ${s.age}` : ""}</td>
                  <td className="r ph-hide">{exp(it.experience_months)}</td>
                  <td className="r">{it.salary ? `${it.salary.toLocaleString("ru-RU")} ${it.currency === "UZS" ? "so'm" : it.currency}` : "—"}</td>
                  <td className="r"><div className="row" style={{ justifyContent: "flex-end" }}>
                    {it.url && <a className="btn sm" href={it.url} target="_blank" rel="noopener noreferrer">{s.open}</a>}
                    {it.taken ? <span className="badge b-ok">{s.taken}</span> : <button className="btn sm primary" onClick={() => take(it)}>{s.take}</button>}
                  </div></td>
                </tr>
              ))}</tbody>
            </table></div>
          )}
        </section>
      )}
    </>
  );
}
