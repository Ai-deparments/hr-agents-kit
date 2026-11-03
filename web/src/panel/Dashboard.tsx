import { lazy, Suspense, useContext, useState } from "react";
import { AlarmClock, ArrowRight, Briefcase, Building2, ChevronDown, ChevronUp, ListChecks, MapPin, UserX, Users } from "lucide-react";
import { LangCtx } from "../i18n";
import { Ic } from "../icons";
import { AnimatedValue } from "../components/AnimatedValue";
import { Empty, Err, useLoad } from "../ui";
import AgentBox from "./AgentBox";
import TileExplain from "./TileExplain";
import { can, usePanel } from "./ctx";

type Day = { day: string; came: number; scheduled: number; late: number };
type D = {
  date: string; active: number; fund: number | null; salaried: number | null; on_shift_today: number; scheduled_today: number; late_today: number;
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
const AttendanceChart = lazy(() => import("../components/charts").then((m) => ({ default: m.AttendanceChart })));

type Audit = { id: number; ts: string; actor: string; action: string; target: string | null };

const L = {
  uz: { active: "Faol xodimlar", probation: "sinov muddatida", shift: "Bugun smenada", notMarked: "belgilanmagan", fund: "Ish haqi fondi",
    mln: "mln", base: "asosiy oyliklar", regs: "Botdan arizalar", cand: "yangi nomzod", att: "Davomat", att14: "so'nggi 14 kun",
    came: "Keldi", plan: "Reja", late: "Kechikdi", early: "30 kunda ketgan", left: "3 oyda ketgan", branches: "Filiallar",
    vacs: "Ochiq vakansiyalar", activity: "Faoliyat", onb: "Onboarding", inPlan: "Rejada", behind: "Ortda", noMentor: "Mentorsiz",
    upd: "Yangilandi", today: "bugun", share: "ulush", docs: "hujjat muddati tugaydi", req: "so'rov kutmoqda", depts: "Bo'limlar", people: "xodim", noDept: "Bo'limsiz", more: "Yana", less: "Yig'ish", all: "Hammasi",
    nCand: "nomzod", days: "kun" },
  ru: { active: "Активные сотрудники", probation: "на испытательном", shift: "На смене сегодня", notMarked: "не отметились", fund: "Фонд оплаты",
    mln: "млн", base: "базовые оклады", regs: "Заявки из бота", cand: "новых кандидатов", att: "Посещаемость", att14: "последние 14 дней",
    came: "Пришли", plan: "План", late: "Опоздали", early: "ушли в первые 30 дней", left: "уволились за 3 мес.", branches: "Филиалы",
    vacs: "Открытые вакансии", activity: "Активность", onb: "Онбординг", inPlan: "В плане", behind: "Отстают", noMentor: "Без наставника",
    upd: "Обновлено", today: "сегодня", share: "доля", docs: "документов истекает", req: "заявлений ждут", depts: "Отделы", people: "сотр.", noDept: "Без отдела", more: "Ещё", less: "Свернуть", all: "Все",
    nCand: "канд.", days: "дн." },
};

function Kpi({ label, value, unit, chip, delta, cmp, icon, hero, onOpen }: {
  label: string; value: string | number; unit?: string; chip?: string; delta?: string; cmp?: string; icon: string; hero?: boolean;
  onOpen?: () => void;
}) {
  return (
    <div className={`span-3 card kpi${hero ? " kpi-hero" : ""}${onOpen ? " kpi-click" : ""}`} onClick={onOpen}
      role={onOpen ? "button" : undefined} tabIndex={onOpen ? 0 : undefined} title={onOpen ? "Qayerdan olinadi?" : undefined}
      onKeyDown={(e) => { if (onOpen && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onOpen(); } }}>
      <span className="kpi-ghost"><Ic n={icon} size={48} /></span>
      <span className="kpi-l">{label}</span>
      <span className="kpi-v"><AnimatedValue value={value} />{unit && <span className="u">{unit}</span>}</span>
      {chip && <span className="chip-dot">{chip}</span>}
      {(delta || cmp) && <div className="cmp">{delta && <span className="dp acc">{delta}</span>} {cmp}</div>}
    </div>
  );
}

type Row = { key: string; name: string; tag?: string; value: number; icon: typeof MapPin };

/** Ranked bars, biggest first; long lists fold after `top` rows. */
function RankList({ rows, top, s }: { rows: Row[]; top: number; s: (typeof L)["uz"] }) {
  const [open, setOpen] = useState(false);
  const sorted = [...rows].sort((a, b) => b.value - a.value);
  const max = Math.max(1, ...sorted.map((r) => r.value));
  const shown = open ? sorted : sorted.slice(0, top);
  return (
    <>
      <ul className="rank rank-i">
        {shown.map(({ key, name, tag, value, icon: I }) => (
          <li key={key}>
            <span className="named"><I className="ic" size={15} aria-hidden="true" /><span className="nm">{name}</span>
              {tag && <span className="tag">{tag}</span>}</span>
            <span className="bar"><i style={{ width: `${(100 * value) / max}%` }} /></span><span className="v">{value}</span>
          </li>
        ))}
      </ul>
      {sorted.length > top && (
        <button className="lnk lnk-i fold" onClick={() => setOpen(!open)}>
          {open ? <>{s.less}<ChevronUp size={14} aria-hidden="true" /></>
            : <>{s.more} {sorted.length - top}<ChevronDown size={14} aria-hidden="true" /></>}
        </button>
      )}
    </>
  );
}

export default function Dashboard() {
  const { lang } = useContext(LangCtx);
  const s = lang === "uz" ? L.uz : L.ru;
  const { me, go } = usePanel();
  const { data: d, error } = useLoad<D>("/api/dashboard");
  const [tile, setTile] = useState<string | null>(null);
  const audit = useLoad<Audit[]>(can(me, "audit.read") ? "/api/audit?limit=6" : null);
  if (error) return <Err e={error} />;
  if (!d) return <div className="empty">…</div>;

  const mln = (v: number | null) => (v === null ? "—" : (v / 1e6).toLocaleString("ru-RU", { maximumFractionDigits: 1 }));
  const pct = (a: number, b: number) => (b ? `${Math.round((100 * a) / b)}%` : "—");
  const now = new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const last7 = d.days.slice(-7);
  const sum = (k: keyof Day, arr: Day[]) => arr.reduce((a, x) => a + (x[k] as number), 0);
  const ago = (ts: string) => {
    const m = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
    return m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} d`;
  };

  return (
    <>
      <div className="grid">
        <Kpi icon="team" label={s.active} value={d.active} chip={`${d.headcount.probation} ${s.probation}`}
          delta={pct(d.headcount.probation, d.active)} cmp={`${d.turnover.left} ${s.left}`} onOpen={() => setTile("active")} />
        <Kpi icon="clock" label={s.shift} value={`${d.on_shift_today} / ${d.scheduled_today}`} chip={`${d.unmarked_today} ${s.notMarked}`}
          delta={pct(d.on_shift_today, d.scheduled_today)} cmp={`${d.late_today} ${s.late.toLowerCase()}`} onOpen={() => setTile("shift")} />
        <Kpi icon="wallet" label={s.fund} value={mln(d.fund)} unit={s.mln} chip={s.base}
          delta={d.fund !== null && d.salaried ? `${mln(Math.round(d.fund / d.salaried))} ${s.mln}` : undefined}
          cmp={lang === "uz" ? "o'rtacha oylik" : "средний оклад"} onOpen={() => setTile("fund")} />
        <Kpi hero icon="inbox" label={s.regs} value={d.registrations_pending ?? "—"} chip={`${d.new_candidates} ${s.cand}`}
          delta={`${d.pending_requests}`} cmp={s.req} onOpen={() => setTile("inbox")} />
      </div>

      <AgentBox lang={lang} />
      {tile && <TileExplain tile={tile} onClose={() => setTile(null)} />}

      <section className="card">
        <div className="card-h"><span className="card-t">{s.att}</span><span className="card-s">{s.att14}</span>
          <span className="card-a"><button className="lnk lnk-i" onClick={() => go("attendance")}>{s.all}<ArrowRight size={14} aria-hidden="true" /></button></span></div>
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
        <Suspense fallback={<div className="viz" />}>
          <AttendanceChart days={d.days} lang={lang} labels={{ came: s.came, plan: s.plan, late: s.late }} />
        </Suspense>
        <div className="legend-dots"><span><i style={{ ["--c" as any]: "var(--viz-1)" }} />{s.came}</span>
          <span><i style={{ ["--c" as any]: "var(--viz-2)" }} />{s.plan}</span></div>
      </section>

      <div className="grid">
        <section className="span-4 card">
          <div className="card-h"><span className="card-t">{s.branches}</span>
            <span className="card-s">{d.branches.reduce((a, b) => a + b.people, 0)} {s.people}</span></div>
          <RankList s={s} top={6} rows={d.branches.map((b) => {
            const [name, tag] = b.branch.split(" · ");
            return { key: b.branch, name, tag, value: b.people, icon: tag ? MapPin : Building2 };
          })} />
          <div className="card-h dash-sub"><span className="card-t">{s.depts}</span></div>
          <RankList s={s} top={5} rows={Object.entries(d.departments).map(([k, v]) => (
            { key: k, name: k === "—" ? s.noDept : k, value: v, icon: Users }))} />
        </section>

        <section className="span-4 card">
          <div className="card-h"><span className="card-t">{s.vacs}</span>
            <span className="card-a"><button className="lnk lnk-i" onClick={() => go("recruiting")}>{s.all}<ArrowRight size={14} aria-hidden="true" /></button></span></div>
          {d.vacancies.length === 0 ? <Empty /> : d.vacancies.map((v) => (
            <div key={v.id} className="vac-row">
              <span className="ico-tile"><Briefcase size={16} aria-hidden="true" /></span>
              <span className="vac-main"><b>{v.title}</b>
                <span className="small muted">{[v.branch, `${v.candidates} ${s.nCand}`].filter(Boolean).join(" · ")}</span></span>
              <span className={`badge ${v.light === "red" ? "b-bad" : v.light === "yellow" ? "b-warn" : "b-ok"}`}
                title="SLA">{v.days_open} / {v.sla_days} {s.days}</span>
            </div>
          ))}
          <div className="card-h dash-sub"><span className="card-t">{s.onb}</span></div>
          <div className="mini-stats">
            {([[ListChecks, s.inPlan, d.onboarding.total, ""],
               [AlarmClock, s.behind, d.onboarding.behind, d.onboarding.behind ? "t-bad" : ""],
               [UserX, s.noMentor, d.onboarding.no_mentor, ""]] as const).map(([I, label, v, cls]) => (
              <div key={label} className="mini-stat"><I size={16} aria-hidden="true" /><b className={cls}>{v}</b><span>{label}</span></div>
            ))}
          </div>
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
