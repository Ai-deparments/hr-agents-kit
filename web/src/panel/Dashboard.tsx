import { useContext } from "react";
import { LangCtx } from "../i18n";
import { Ic } from "../icons";
import { AnimatedValue } from "../components/AnimatedValue";
import { Empty, Err, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

type Day = { day: string; came: number; scheduled: number; late: number };
type D = {
  date: string; active: number; fund: number | null; on_shift_today: number; scheduled_today: number; late_today: number;
  unmarked_today: number; pending_requests: number; new_candidates: number; pending_approvals: number; documents_30d: number;
  registrations_pending: number | null;
  headcount: { total: number; probation: number };
  departments: Record<string, number>;
  turnover: { left: number; base: number; left_first_30_days: number };
  onboarding: { total: number; behind: number; no_mentor: number; no_test: number };
  branches: { branch: string; people: number; fund: number | null }[];
  vacancies: { id: number; title: string; branch: string | null; days_open: number; sla_days: number; light: string; candidates: number }[];
  days: Day[];
};
type Audit = { id: number; ts: string; actor: string; action: string; target: string | null };

const L = {
  uz: { active: "Faol xodimlar", probation: "sinov muddatida", shift: "Bugun smenada", notMarked: "belgilanmagan", fund: "Ish haqi fondi",
    mln: "mln", base: "asosiy oyliklar", regs: "Botdan arizalar", cand: "yangi nomzod", att: "Davomat", att14: "so'nggi 14 kun",
    came: "Keldi", plan: "Reja", late: "Kechikdi", early: "30 kunda ketgan", left: "3 oyda ketgan", branches: "Filiallar",
    vacs: "Ochiq vakansiyalar", activity: "Faoliyat", onb: "Onboarding", inPlan: "Rejada", behind: "Ortda", noMentor: "Mentorsiz",
    upd: "Yangilandi", today: "bugun", share: "ulush", docs: "hujjat muddati tugaydi", req: "so'rov kutmoqda", depts: "Bo'limlar", people: "xodim" },
  ru: { active: "Активные сотрудники", probation: "на испытательном", shift: "На смене сегодня", notMarked: "не отметились", fund: "Фонд оплаты",
    mln: "млн", base: "базовые оклады", regs: "Заявки из бота", cand: "новых кандидатов", att: "Посещаемость", att14: "последние 14 дней",
    came: "Пришли", plan: "План", late: "Опоздали", early: "ушли в первые 30 дней", left: "уволились за 3 мес.", branches: "Филиалы",
    vacs: "Открытые вакансии", activity: "Активность", onb: "Онбординг", inPlan: "В плане", behind: "Отстают", noMentor: "Без наставника",
    upd: "Обновлено", today: "сегодня", share: "доля", docs: "документов истекает", req: "заявлений ждут", depts: "Отделы", people: "сотр." },
};

/** Bars = came, smooth area = planned. Pure SVG, colours from CSS. */
function Combo({ days, lang }: { days: Day[]; lang: string }) {
  const W = 1000, H = 240, pl = 34, pb = 26, pt = 10;
  const max = Math.max(1, ...days.map((d) => Math.max(d.came, d.scheduled)));
  const top = Math.ceil(max / 5) * 5 || 5;
  const step = (W - pl) / days.length;
  const x = (i: number) => pl + step * i + step / 2;
  const y = (v: number) => pt + (H - pt - pb) * (1 - v / top);
  const pts = days.map((d, i) => [x(i), y(d.scheduled)]);
  let path = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 0; i < pts.length - 1; i++) {  // Catmull-Rom -> cubic Bézier
    const [p0, p1, p2, p3] = [pts[i - 1] || pts[i], pts[i], pts[i + 1], pts[i + 2] || pts[i + 1]];
    path += ` C${p1[0] + (p2[0] - p0[0]) / 6},${p1[1] + (p2[1] - p0[1]) / 6} ${p2[0] - (p3[0] - p1[0]) / 6},${p2[1] - (p3[1] - p1[1]) / 6} ${p2[0]},${p2[1]}`;
  }
  const area = `${path} L${pts[pts.length - 1][0]},${y(0)} L${pts[0][0]},${y(0)} Z`;
  const bw = Math.min(34, step * 0.5);
  const fmt = (iso: string) => new Date(iso + "T12:00:00").toLocaleDateString(lang === "en" ? "en-GB" : "ru-RU", { day: "2-digit", month: "2-digit" });
  return (
    <svg className="combo" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label="attendance">
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <g key={f}><line className="gl" x1={pl} x2={W} y1={y(top * f)} y2={y(top * f)} />
          <text x={pl - 8} y={y(top * f) + 4} textAnchor="end">{Math.round(top * f)}</text></g>
      ))}
      {days.map((_, i) => <line key={i} className="gl" x1={x(i)} x2={x(i)} y1={pt} y2={y(0)} />)}
      <path className="area" d={area} />
      {days.map((d, i) => (
        <g key={d.day}>
          <rect className="b" x={x(i) - bw / 2} y={y(d.came)} width={bw} height={Math.max(0, y(0) - y(d.came))} rx={2}>
            <title>{`${fmt(d.day)}: ${d.came} / ${d.scheduled}`}</title></rect>
          <text x={x(i)} y={H - 6} textAnchor="middle">{fmt(d.day)}</text>
        </g>
      ))}
    </svg>
  );
}

function Kpi({ label, value, unit, chip, delta, cmp, icon, hero }: {
  label: string; value: string | number; unit?: string; chip?: string; delta?: string; cmp?: string; icon: string; hero?: boolean;
}) {
  return (
    <div className={`span-3 card kpi${hero ? " kpi-hero" : ""}`}>
      <span className="kpi-ghost"><Ic n={icon} size={48} /></span>
      <span className="kpi-l">{label}</span>
      <span className="kpi-v"><AnimatedValue value={value} />{unit && <span className="u">{unit}</span>}</span>
      {chip && <span className="chip-dot">{chip}</span>}
      {(delta || cmp) && <div className="cmp">{delta && <span className="dp acc">{delta}</span>} {cmp}</div>}
    </div>
  );
}

export default function Dashboard() {
  const { lang } = useContext(LangCtx);
  const s = lang === "uz" ? L.uz : L.ru;
  const { me, go } = usePanel();
  const { data: d, error } = useLoad<D>("/api/dashboard");
  const audit = useLoad<Audit[]>(can(me, "audit.read") ? "/api/audit?limit=6" : null);
  if (error) return <Err e={error} />;
  if (!d) return <div className="empty">…</div>;

  const mln = (v: number | null) => (v === null ? "—" : (v / 1e6).toLocaleString("ru-RU", { maximumFractionDigits: 1 }));
  const pct = (a: number, b: number) => (b ? `${Math.round((100 * a) / b)}%` : "—");
  const now = new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const last7 = d.days.slice(-7);
  const sum = (k: keyof Day, arr: Day[]) => arr.reduce((a, x) => a + (x[k] as number), 0);
  const maxB = Math.max(1, ...d.branches.map((b) => b.people));
  const ago = (ts: string) => {
    const m = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
    return m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} d`;
  };

  return (
    <>
      <div className="grid">
        <Kpi icon="team" label={s.active} value={d.active} chip={`${d.headcount.probation} ${s.probation}`}
          delta={pct(d.headcount.probation, d.active)} cmp={`${d.turnover.left} ${s.left}`} />
        <Kpi icon="clock" label={s.shift} value={`${d.on_shift_today} / ${d.scheduled_today}`} chip={`${d.unmarked_today} ${s.notMarked}`}
          delta={pct(d.on_shift_today, d.scheduled_today)} cmp={`${d.late_today} ${s.late.toLowerCase()}`} />
        <Kpi icon="wallet" label={s.fund} value={mln(d.fund)} unit={s.mln} chip={s.base}
          delta={d.fund !== null && d.active ? `${mln(Math.round(d.fund / d.active))} ${s.mln}` : undefined}
          cmp={lang === "uz" ? "o'rtacha oylik" : "средний оклад"} />
        <Kpi hero icon="inbox" label={s.regs} value={d.registrations_pending ?? "—"} chip={`${d.new_candidates} ${s.cand}`}
          delta={`${d.pending_requests}`} cmp={s.req} />
      </div>

      <section className="card">
        <div className="card-h"><span className="card-t">{s.att}</span><span className="card-s">{s.att14}</span>
          <span className="card-a"><button className="lnk" onClick={() => go("attendance")}>→</button></span></div>
        <div className="row att-stats" style={{ gap: "18px 48px", marginBottom: 8 }}>
          {[
            [sum("came", last7), s.came, pct(sum("came", last7), sum("scheduled", last7))],
            [sum("scheduled", last7), s.plan, "7 d"],
            [sum("late", last7), s.late, pct(sum("late", last7), sum("came", last7))],
            [d.documents_30d, s.docs, "30 d"],
          ].map(([v, label, chip]) => (
            <div key={String(label)} className="kpi" style={{ minWidth: 150, containerType: "normal" }}>
              <span className="kpi-v">{v}</span>
              <span className="chip-dot">{label}</span>
              <div className="cmp"><span className="dp acc">{chip}</span></div>
            </div>
          ))}
        </div>
        <Combo days={d.days} lang={lang} />
        <div className="legend-dots"><span><i style={{ ["--c" as any]: "var(--accent)" }} />{s.came}</span>
          <span><i style={{ ["--c" as any]: "var(--data-2)" }} />{s.plan}</span></div>
      </section>

      <div className="grid">
        <section className="span-4 card">
          <div className="card-h"><span className="card-t">{s.branches}</span></div>
          <ol className="rank">
            {d.branches.map((b, i) => (
              <li key={b.branch}><span className="n">{i + 1}</span>
                <span className="named"><span className="mk">{b.branch.replace(/[^A-Za-zА-Яа-я0-9]/g, "").slice(0, 2).toUpperCase()}</span>{b.branch}</span>
                <span className="bar"><i style={{ width: `${(100 * b.people) / maxB}%` }} /></span><span className="v">{b.people}</span></li>
            ))}
          </ol>
          <dl className="kv" style={{ marginTop: 12 }}>
            {Object.entries(d.departments).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
          </dl>
        </section>

        <section className="span-4 card">
          <div className="card-h"><span className="card-t">{s.vacs}</span>
            <span className="card-a"><button className="lnk" onClick={() => go("recruiting")}>→</button></span></div>
          {d.vacancies.length === 0 ? <Empty /> : d.vacancies.map((v) => (
            <div key={v.id} className="named" style={{ display: "flex", padding: "10px 0", borderBottom: "1px solid var(--grid)" }}>
              <span className="avatar">{v.title.slice(0, 2).toUpperCase()}</span>
              <span style={{ flex: 1, minWidth: 0 }}><b style={{ fontWeight: 600 }}>{v.title}</b>
                <span className="small muted" style={{ display: "block" }}>{v.branch} · {v.candidates} cand.</span></span>
              <span className={`badge ${v.light === "red" ? "b-bad" : v.light === "yellow" ? "b-warn" : "b-ok"}`}>{v.days_open}/{v.sla_days} d</span>
            </div>
          ))}
          <dl className="kv" style={{ marginTop: 14 }}>
            <div><dt>{s.onb}: {s.inPlan}</dt><dd>{d.onboarding.total}</dd></div>
            <div><dt>{s.behind}</dt><dd className={d.onboarding.behind ? "t-bad" : ""}>{d.onboarding.behind}</dd></div>
            <div><dt>{s.noMentor}</dt><dd>{d.onboarding.no_mentor}</dd></div>
          </dl>
        </section>

        <section className="span-4 card">
          <div className="card-h"><span className="card-t">{s.activity}</span><span className="card-s">{s.upd} {s.today}, {now}</span></div>
          {audit.data && audit.data.length > 0 ? (
            <ul className="tl">
              {audit.data.map((a) => (
                <li key={a.id}><div className="when">{ago(a.ts)}</div>
                  <div>{a.actor.replace(/^user:|^tg:/, "")} — <b>{a.action.replace(/_/g, " ")}</b></div>
                  {a.target && <div className="small muted">{a.target}</div>}</li>
              ))}
            </ul>
          ) : <Empty />}
        </section>
      </div>
    </>
  );
}
