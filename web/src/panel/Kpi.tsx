import { lazy, Suspense, useContext, useMemo, useState } from "react";
import { api, download, money, monthISO } from "../api";
import { LangCtx, useT } from "../i18n";
import { Ic } from "../icons";
import { AnimatedValue } from "../components/AnimatedValue";
import { Empty, Err, Modal, ReasonModal, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

type Metric = { id: number; name: string; unit: string; direction: "up" | "down"; target: number; weight: number;
  position_id: number | null; department_id: number | null; active: boolean };
type Row = { employee_id: number; full_name: string; branch: string | null; department: string | null; position: string | null;
  metrics: number[]; values: Record<string, number>; score: number | null; filled: number; applicable: number };
type Grid = { month: string; metrics: Metric[]; rows: Row[]; avg: number | null; scored: number; total: number };
type AbcRow = { rank: number; employee_id: number; full_name: string; branch: string | null; department: string | null;
  value: number; share: number; cum_share: number; class: "A" | "B" | "C" };
type Abc = { rows: AbcRow[]; total: number; n: number; too_few: boolean; counts: Record<string, number>;
  class_share: Record<string, number>; pareto: { top_pct: number; top_n: number; top_share: number | null };
  settings: { abc_a: number; abc_b: number; pareto_top: number; min_base: number }; missing: number };
type Trend = { month: string; avg: number | null; scored: number; total: number }[];
type SalesRow = { rank: number; employee_id: number; full_name: string; branch: string | null; amount: number; share: number;
  class: "A" | "B" | "C"; prev_amount: number | null; delta_pct: number | null };
type Sales = { month: string; prev_month: string; partial: boolean; n: number; total: number | null; delta_pct: number | null;
  counts: Record<string, number>; pareto: { top_pct: number; top_n: number; top_share: number | null };
  plan: number | null; plan_pct: number | null; rows: SalesRow[] };
type FileRow = { id: number; title: string; month: string | null; kind: string; filename: string; size: number; uploaded_by: string; created_at: string };

const T = {
  uz: { dash: "BI-tahlil", values: "KPI kiritish", metrics: "KPI ko'rsatkichlari", reports: "Hisobotlar", settings: "Sozlamalar",
    avg: "O'rtacha KPI", filled: "KPI to'ldirilgan", classA: "A guruh", pareto: "80/20", top: "eng yaxshi", give: "natijaning",
    trend: "KPI dinamikasi", trendS: "o'rtacha ball, oxirgi 6 oy", abc: "ABC tahlil", basis: "Asos", byKpi: "KPI ball", bySales: "Shaxsiy sotuv",
    employee: "Xodim", value: "Qiymat", share: "Ulush", cum: "Yig'ma", cls: "Guruh", tooFew: "juda kam ma'lumot", noData: "ma'lumot yo'q",
    save: "Saqlash", apply: "Oylikka o'tkazish", excel: "Excel", changed: "o'zgargan", target: "Maqsad", weight: "Vazn", dir: "Yo'nalish",
    up: "ko'p — yaxshi", down: "kam — yaxshi", unit: "Birlik", forPos: "Lavozim", forDept: "Bo'lim", everyone: "Hammaga", active: "Faol",
    upload: "Yuklash", title: "Nomi", kind: "Turi", file: "Fayl", month: "Oy", dept: "Bo'lim", all: "Hammasi",
    abcHelp: "A — natijaning birinchi {a}%, B — keyingi {b}%, C — qolgani", paretoHelp: "eng yaxshi {p}% xodim natijaning qancha qismini beradi",
    missing: "KPI yo'q", score: "KPI %" },
  ru: { dash: "BI-аналитика", values: "Ввод KPI", metrics: "Показатели KPI", reports: "Отчёты", settings: "Настройки",
    avg: "Средний KPI", filled: "KPI заполнен", classA: "Группа A", pareto: "80/20", top: "лучших", give: "результата",
    trend: "Динамика KPI", trendS: "средний балл, последние 6 мес.", abc: "ABC-анализ", basis: "Основа", byKpi: "Балл KPI", bySales: "Личные продажи",
    employee: "Сотрудник", value: "Значение", share: "Доля", cum: "Накопл.", cls: "Группа", tooFew: "слишком мало данных", noData: "нет данных",
    save: "Сохранить", apply: "Перенести в зарплату", excel: "Excel", changed: "изменено", target: "Цель", weight: "Вес", dir: "Направление",
    up: "больше — лучше", down: "меньше — лучше", unit: "Ед.", forPos: "Должность", forDept: "Отдел", everyone: "Все", active: "Активен",
    upload: "Загрузить", title: "Название", kind: "Тип", file: "Файл", month: "Месяц", dept: "Отдел", all: "Все",
    abcHelp: "A — первые {a}% результата, B — до {b}%, C — остальное", paretoHelp: "какую долю результата дают лучшие {p}% сотрудников",
    missing: "без KPI", score: "KPI %" },
};

const ParetoChart = lazy(() => import("../components/charts").then((m) => ({ default: m.ParetoChart })));
const fmt = (v: number | null | undefined, d = 1) => (v === null || v === undefined ? "—" : v.toLocaleString("ru-RU", { maximumFractionDigits: d }));

/** Sales agents ranking (Smartup): amount, share, Δ vs previous month, ABC. Unknown = "—". */
function SalesRank({ month }: { month: string }) {
  const t = useT();
  const r = useLoad<Sales>(`/api/kpi/sales?month=${month}`, [month]);
  const d = r.data;
  const pct = (v: number | null) => (v === null ? "—" : `${v > 0 ? "+" : ""}${fmt(v)}%`);
  return (
    <section className="card">
      <div className="card-h"><span className="card-t">{t.l("Savdo agentlari reytingi", "Рейтинг торговых агентов", "Sales agents ranking")}</span>
        <span className="card-s">{d && d.n ? `${d.n} · ${money(d.total)} · A ${d.counts.A} / B ${d.counts.B} / C ${d.counts.C}` +
          (d.pareto.top_share !== null ? ` · ${t.l("top", "топ", "top")} ${d.pareto.top_n} = ${fmt(d.pareto.top_share)}%` : "") +
          (d.plan ? ` · ${t.l("reja", "план", "plan")} ${fmt(d.plan_pct)}%` : "") +
          (d.partial ? ` · ${t.l("oy davom etmoqda", "месяц не закрыт", "month in progress")}` : "") : ""}</span></div>
      <Err e={r.error} />
      {d && d.rows.length ? (
        <div className="tbl-wrap"><table className="tbl">
          <thead><tr><th>#</th><th>{t.l("Agent", "Агент", "Agent")}</th><th className="r">{t.l("Sotuv", "Продажи", "Sales")}</th>
            <th className="r">{t.l("Ulush", "Доля", "Share")}</th><th className="r ph-hide">Δ {d.prev_month}</th><th>ABC</th></tr></thead>
          <tbody>{d.rows.map((x) => (
            <tr key={x.employee_id}>
              <td className="muted">{x.rank}</td>
              <td>{x.full_name}<span className="sub">{x.branch}</span></td>
              <td className="r">{money(x.amount)}</td>
              <td className="r">{fmt(x.share)}%</td>
              <td className="r ph-hide">{pct(x.delta_pct)}</td>
              <td><span className={`badge ${x.class === "A" ? "b-info" : x.class === "C" ? "" : "b-ok"}`}>{x.class}</span></td>
            </tr>
          ))}</tbody>
        </table></div>
      ) : <Empty text={t.l("Bu oy uchun savdo ma'lumoti yo'q", "Нет данных о продажах за месяц", "No sales data for this month")} />}
    </section>
  );
}

/** HTML columns (crisp text at any card width); the 100% target is a dashed line. */
function TrendBars({ data }: { data: Trend }) {
  const max = Math.max(110, ...data.map((d) => d.avg || 0));
  return (
    <div className="tbars">
      <span className="tbars-target" style={{ bottom: `calc(${(100 / max) * 100}% * .82 + 22px)` }}><b>100%</b></span>
      {data.map((d, i) => (
        <div key={d.month} className="tbar">
          <b>{fmt(d.avg)}</b>
          <i style={{ height: d.avg !== null ? `${(d.avg / max) * 82}%` : 0, opacity: i === data.length - 1 ? 0.75 : 1 }} />
          <span>{d.month.slice(5)}.{d.month.slice(2, 4)}</span>
        </div>
      ))}
    </div>
  );
}

function Card({ label, value, unit, chip, note, icon, hero }: { label: string; value: string; unit?: string; chip?: string; note?: string; icon: string; hero?: boolean }) {
  return (
    <div className={`span-3 card kpi${hero ? " kpi-hero" : ""}`}>
      <span className="kpi-ghost"><Ic n={icon} size={44} /></span>
      <span className="kpi-l">{label}</span>
      <span className="kpi-v"><AnimatedValue value={value} />{unit && <span className="u">{unit}</span>}</span>
      {chip && <span className="chip-dot">{chip}</span>}
      {note && <div className="cmp">{note}</div>}
    </div>
  );
}

function Dashboard({ month, dept, s }: { month: string; dept: string; s: typeof T.ru }) {
  const { me } = usePanel();
  const grid = useLoad<Grid>(`/api/kpi/grid?month=${month}${dept ? `&department_id=${dept}` : ""}`, [month, dept]);
  const [basis, setBasis] = useState(me.payroll ? "sales" : "kpi");  // contribution (sales) is the classic ABC base
  const abc = useLoad<Abc>(`/api/kpi/abc?month=${month}&basis=${basis}${dept ? `&department_id=${dept}` : ""}`, [month, dept, basis]);
  const trend = useLoad<Trend>(`/api/kpi/trend?month=${month}${dept ? `&department_id=${dept}` : ""}`, [month, dept]);
  const a = abc.data;
  const upMetrics = (grid.data?.metrics || []).filter((m) => m.direction === "up");
  return (
    <>
      <Err e={grid.error || abc.error || trend.error} />
      <div className="grid">
        <Card hero icon="chart" label={s.avg} value={fmt(grid.data?.avg)} unit="%" chip={`${grid.data?.scored ?? "—"} / ${grid.data?.total ?? "—"}`} note={s.filled} />
        <Card icon="check" label={s.filled} value={grid.data ? `${grid.data.scored}` : "—"} unit={grid.data ? `/ ${grid.data.total}` : ""}
          chip={grid.data ? `${grid.data.total - grid.data.scored} ${s.missing}` : undefined} />
        <Card icon="flag" label={s.classA} value={a ? `${a.counts.A}` : "—"} unit={a ? `/ ${a.n}` : ""}
          chip={a ? `${a.class_share.A}% ${s.give}` : undefined} note={a && a.too_few ? s.tooFew : undefined} />
        <Card icon="spark" label={s.pareto} value={a?.pareto.top_share != null ? `${fmt(a.pareto.top_share)}` : "—"} unit="%"
          chip={a ? `${a.pareto.top_n} ${s.top} (${a.pareto.top_pct}%)` : undefined} note={a ? s.paretoHelp.replace("{p}", String(a.pareto.top_pct)) : undefined} />
      </div>

      <div className="grid">
        <section className="span-4 card">
          <div className="card-h"><span className="card-t">{s.trend}</span><span className="card-s">{s.trendS}</span></div>
          {trend.data ? <TrendBars data={trend.data} /> : <Empty />}
        </section>
        <section className="span-8 card">
          <div className="card-h"><span className="card-t">{s.abc} · {s.pareto}</span>
            <span className="card-s">{a ? s.abcHelp.replace("{a}", String(a.settings.abc_a)).replace("{b}", String(a.settings.abc_b)) : ""}</span>
            <span className="card-a">
              <select className="ctl" value={basis} onChange={(e) => setBasis(e.target.value)} aria-label={s.basis}>
                <option value="kpi">{s.basis}: {s.byKpi}</option>
                {me.payroll && <option value="sales">{s.basis}: {s.bySales}</option>}
                {upMetrics.map((m) => <option key={m.id} value={`metric:${m.id}`}>{s.basis}: {m.name}</option>)}
              </select>
            </span></div>
          {a && a.rows.length ? (
            <Suspense fallback={<div className="viz" />}>
              <ParetoChart rows={a.rows} a={a.settings.abc_a} b={a.settings.abc_b} valueLabel={s.basis} />
            </Suspense>) : <Empty />}
          <div className="legend-dots">
            <span><i style={{ ["--c" as any]: "var(--abc-a)" }} />A {a ? `· ${a.counts.A}` : ""}</span>
            <span><i style={{ ["--c" as any]: "var(--abc-b)" }} />B {a ? `· ${a.counts.B}` : ""}</span>
            <span><i style={{ ["--c" as any]: "var(--abc-c)" }} />C {a ? `· ${a.counts.C}` : ""}</span>
          </div>
        </section>
      </div>

      <section className="card">
        <div className="card-h"><span className="card-t">{s.abc}</span><span className="card-s">{a ? `${a.n} · ${s.noData}: ${a.missing}` : ""}</span></div>
        {a && a.rows.length ? (
          <div className="tbl-wrap"><table className="tbl">
            <thead><tr><th>#</th><th>{s.employee}</th><th className="ph-hide">{s.dept}</th><th className="r">{s.value}</th>
              <th className="r">{s.share}</th><th className="r ph-hide">{s.cum}</th><th>{s.cls}</th></tr></thead>
            <tbody>{a.rows.map((r) => (
              <tr key={r.employee_id}>
                <td className="muted">{r.rank}</td>
                <td><span className="named"><span className="mk">{r.full_name.split(" ").map((p) => p[0]).join("").slice(0, 2)}</span>{r.full_name}</span>
                  <span className="sub">{r.branch}</span></td>
                <td className="ph-hide">{r.department || "—"}</td>
                <td className="r">{fmt(r.value)}</td>
                <td className="r"><span className="cbar"><s><i style={{ width: `${Math.min(100, r.share * 4)}%` }} /></s><b>{fmt(r.share)}%</b></span></td>
                <td className="r ph-hide">{fmt(r.cum_share)}%</td>
                <td><span className={`badge ${r.class === "A" ? "b-info" : r.class === "C" ? "" : "b-ok"}`}>{r.class}</span></td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <Empty text={s.noData} />}
      </section>
      {can(me, "analytics") && <SalesRank month={month} />}
    </>
  );
}

function Values({ month, dept, s }: { month: string; dept: string; s: typeof T.ru }) {
  const { me } = usePanel();
  const grid = useLoad<Grid>(`/api/kpi/grid?month=${month}${dept ? `&department_id=${dept}` : ""}`, [month, dept]);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [apply, setApply] = useState(false);
  const write = can(me, "analytics") || can(me, "payroll.write");
  const g = grid.data;
  const key = (e: number, m: number) => `${e}:${m}`;
  const n = Object.keys(edits).length;
  const save = async () => {
    setErr(null);
    try {
      const values = Object.entries(edits).map(([k, v]) => {
        const [e, m] = k.split(":").map(Number);
        return { employee_id: e, metric_id: m, value: v.trim() === "" ? null : Number(v.replace(",", ".")) };
      });
      if (values.some((v) => v.value !== null && Number.isNaN(v.value))) throw new Error("Raqam kiriting / Введите число");
      const r = await api<{ changed: number }>("/api/kpi/values", { body: { month, values } });
      setEdits({}); setMsg(`${s.save}: ${r.changed}`); grid.reload();
    } catch (x: any) { setErr(x.message); }
  };
  if (!g) return <Err e={grid.error} />;
  return (
    <section className="card">
      <div className="card-h"><span className="card-t">{s.values}</span>
        <span className="card-s">{g.scored} / {g.total} · {s.avg}: {fmt(g.avg)}%</span>
        <span className="card-a">
          <button className="btn sm" onClick={() => download(`/api/kpi/excel?month=${month}${dept ? `&department_id=${dept}` : ""}`, `kpi-${month}.xlsx`)}>
            <Ic n="file" />{s.excel}</button>
          {can(me, "payroll.write") && <button className="btn sm" onClick={() => setApply(true)}><Ic n="wallet" />{s.apply}</button>}
          {write && <button className="btn sm primary" disabled={!n} onClick={save}>{s.save}{n ? ` · ${n}` : ""}</button>}
        </span></div>
      <Err e={err} />{msg && <div className="note">{msg}</div>}
      <div className="tbl-wrap"><table className="tbl">
        <thead><tr><th>{s.employee}</th>
          {g.metrics.map((m) => <th key={m.id} className="r" title={`${s.target}: ${m.target} · ${s.weight}: ${m.weight}`}>
            {m.name}<span className="sub">{m.direction === "down" ? "≤" : "≥"} {m.target} {m.unit} · {m.weight}</span></th>)}
          <th className="r">{s.score}</th></tr></thead>
        <tbody>{g.rows.map((r) => (
          <tr key={r.employee_id}>
            <td>{r.full_name}<span className="sub">{r.position} · {r.branch}</span></td>
            {g.metrics.map((m) => {
              const k = key(r.employee_id, m.id);
              if (!r.metrics.includes(m.id)) return <td key={m.id} className="r muted">·</td>;
              const v = edits[k] ?? (r.values[String(m.id)] ?? "").toString();
              return <td key={m.id} className="r">
                <input className="kpi-in" inputMode="decimal" disabled={!write} value={v} aria-label={`${r.full_name} ${m.name}`}
                  onChange={(e) => setEdits({ ...edits, [k]: e.target.value })} style={edits[k] !== undefined ? { borderColor: "var(--accent)" } : undefined} /></td>;
            })}
            <td className="r"><b className={r.score !== null && r.score < 70 ? "t-bad" : ""}>{fmt(r.score)}</b>
              <span className="sub">{r.filled}/{r.applicable}</span></td>
          </tr>
        ))}</tbody>
      </table></div>
      {apply && <ReasonModal title={`${s.apply} · ${month}`} onClose={() => setApply(false)}
        onSubmit={(reason) => api<{ applied: number }>(`/api/kpi/${month}/apply`, { body: { reason } }).then((r) => setMsg(`${s.apply}: ${r.applied}`))} />}
    </section>
  );
}

function MetricEditor({ m, onClose, onDone, s }: { m: Metric | null; onClose: () => void; onDone: () => void; s: typeof T.ru }) {
  const t = useT();
  const { dicts } = usePanel();
  const [f, setF] = useState({ name: m?.name || "", unit: m?.unit || "%", direction: m?.direction || "up", target: String(m?.target ?? 100),
    weight: String(m?.weight ?? 10), position_id: m?.position_id ? String(m.position_id) : "", department_id: m?.department_id ? String(m.department_id) : "",
    active: m?.active ?? true });
  const [err, setErr] = useState<string | null>(null);
  return (
    <Modal title={m ? m.name : `${t("add")}: KPI`} onClose={onClose}>
      <div className="stack">
        <label className="field">{s.title}<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <div className="grid two">
          <label className="field">{s.dir}<select value={f.direction} onChange={(e) => setF({ ...f, direction: e.target.value as "up" | "down" })}>
            <option value="up">{s.up}</option><option value="down">{s.down}</option></select></label>
          <label className="field">{s.unit}<input value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} /></label>
          <label className="field">{s.target}<input inputMode="decimal" value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} /></label>
          <label className="field">{s.weight}<input inputMode="numeric" value={f.weight} onChange={(e) => setF({ ...f, weight: e.target.value })} /></label>
          <label className="field">{s.forPos}<select value={f.position_id} onChange={(e) => setF({ ...f, position_id: e.target.value })}>
            <option value="">{s.everyone}</option>{dicts.positions.map((p) => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
          <label className="field">{s.forDept}<select value={f.department_id} onChange={(e) => setF({ ...f, department_id: e.target.value })}>
            <option value="">{s.everyone}</option>{dicts.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
        </div>
        <label className="check"><input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /><span><b>{s.active}</b></span></label>
        <Err e={err} />
        <div className="row"><span className="spacer" />
          <button className="btn" onClick={onClose}>{t("cancel")}</button>
          <button className="btn primary" onClick={async () => {
            const body = { ...f, target: Number(f.target.replace(",", ".")), weight: Number(f.weight),
              position_id: f.position_id ? Number(f.position_id) : null, department_id: f.department_id ? Number(f.department_id) : null };
            try { await (m ? api(`/api/kpi/metrics/${m.id}`, { method: "PATCH", body }) : api("/api/kpi/metrics", { body })); onDone(); onClose(); }
            catch (x: any) { setErr(x.message); }
          }}>{t("save")}</button>
        </div>
      </div>
    </Modal>
  );
}

function Metrics({ s }: { s: typeof T.ru }) {
  const t = useT();
  const { me, dicts } = usePanel();
  const list = useLoad<Metric[]>("/api/kpi/metrics");
  const st = useLoad<Abc["settings"]>("/api/kpi/settings");
  const [edit, setEdit] = useState<Metric | "new" | null>(null);
  const [cfg, setCfg] = useState<Record<string, string> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const write = can(me, "analytics");
  const pos = (id: number | null) => (id ? dicts.positions.find((p) => p.id === id)?.title : s.everyone);
  const dep = (id: number | null) => (id ? dicts.departments.find((d) => d.id === id)?.name : s.everyone);
  const vals = cfg || (st.data ? Object.fromEntries(Object.entries(st.data).map(([k, v]) => [k, String(v)])) : null);
  const total = (list.data || []).filter((m) => m.active && !m.position_id && !m.department_id).reduce((a, m) => a + m.weight, 0);
  return (
    <div className="grid">
      <section className="span-8 card">
        <div className="card-h"><span className="card-t">{s.metrics}</span><span className="card-s">{s.weight}: {total} ({t.l("umumiy", "общие", "common")})</span>
          <span className="card-a">{write && <button className="btn sm primary" onClick={() => setEdit("new")}>+ {t("add")}</button>}</span></div>
        <Err e={list.error} />
        <div className="tbl-wrap"><table className="tbl">
          <thead><tr><th>{s.title}</th><th>{s.dir}</th><th className="r">{s.target}</th><th className="r">{s.weight}</th><th>{s.forPos}</th><th className="ph-hide">{s.forDept}</th><th /></tr></thead>
          <tbody>{(list.data || []).map((m) => (
            <tr key={m.id} style={m.active ? undefined : { opacity: 0.5 }}>
              <td>{m.name}</td><td className="small">{m.direction === "up" ? s.up : s.down}</td>
              <td className="r">{fmt(m.target, 2)} {m.unit}</td><td className="r">{m.weight}</td>
              <td className="small">{pos(m.position_id)}</td><td className="small ph-hide">{dep(m.department_id)}</td>
              <td className="r">{write && <button className="btn sm" onClick={() => setEdit(m)}>{t("edit")}</button>}</td>
            </tr>
          ))}</tbody>
        </table></div>
        <p className="card-f">KPI % = Σ ({s.weight} × min(fakt / {s.target}, 1.2)) / Σ {s.weight} · {s.down}: {s.target} / fakt</p>
      </section>
      <section className="span-4 card">
        <div className="card-h"><span className="card-t">{s.settings}</span></div>
        {vals && <div className="stack">
          {[["abc_a", "A ≤ %"], ["abc_b", "B ≤ %"], ["pareto_top", "Pareto top %"], ["min_base", "min n"]].map(([k, label]) => (
            <label key={k} className="field">{label}<input inputMode="numeric" disabled={!write} value={vals[k]}
              onChange={(e) => setCfg({ ...vals, [k]: e.target.value })} /></label>
          ))}
          <Err e={err} />
          {write && <button className="btn primary" disabled={!cfg} onClick={async () => {
            try { await api("/api/kpi/settings", { method: "PUT", body: Object.fromEntries(Object.entries(vals).map(([k, v]) => [k, Number(v)])) });
              setCfg(null); setErr(null); st.reload(); } catch (x: any) { setErr(x.message); }
          }}>{s.save}</button>}
        </div>}
      </section>
      {edit && <MetricEditor m={edit === "new" ? null : edit} s={s} onClose={() => setEdit(null)} onDone={list.reload} />}
    </div>
  );
}

function Reports({ s }: { s: typeof T.ru }) {
  const t = useT();
  const { me } = usePanel();
  const list = useLoad<FileRow[]>("/api/kpi/reports");
  const [f, setF] = useState({ title: "", month: monthISO(), kind: "kpi" });
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const write = can(me, "analytics");
  const kb = (n: number) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB`);
  return (
    <div className="grid">
      {write && <section className="span-4 card">
        <div className="card-h"><span className="card-t">{s.upload}</span><span className="card-s">xlsx · csv · pdf · docx · pptx · png/jpg · ≤ 5 MB</span></div>
        <div className="stack">
          <label className="field">{s.title}<input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></label>
          <label className="field">{s.month}<input type="month" value={f.month} onChange={(e) => setF({ ...f, month: e.target.value })} /></label>
          <label className="field">{s.kind}<select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
            <option value="kpi">KPI</option><option value="abc">ABC / 80-20</option><option value="payroll">Payroll</option><option value="other">Other</option></select></label>
          <label className="field">{s.file}<input type="file" accept=".xlsx,.xls,.csv,.pdf,.docx,.pptx,.png,.jpg" onChange={(e) => setFile(e.target.files?.[0] || null)} style={{ height: "auto" }} /></label>
          <Err e={err} />
          <button className="btn primary" disabled={!file || busy} onClick={async () => {
            if (!file) return;
            setBusy(true); setErr(null);
            const form = new FormData(); form.append("file", file);
            const q = new URLSearchParams({ title: f.title, kind: f.kind, ...(f.month ? { month: f.month } : {}) });
            try { await api(`/api/kpi/reports?${q}`, { form }); setFile(null); setF({ ...f, title: "" }); list.reload(); }
            catch (x: any) { setErr(x.message); } finally { setBusy(false); }
          }}>{s.upload}</button>
        </div>
      </section>}
      <section className={`${write ? "span-8" : "span-12"} card`}>
        <div className="card-h"><span className="card-t">{s.reports}</span><span className="card-s">{list.data?.length ?? 0}</span></div>
        {list.data && list.data.length ? (
          <div className="tbl-wrap"><table className="tbl">
            <thead><tr><th>{s.title}</th><th>{s.kind}</th><th>{s.month}</th><th className="r ph-hide">KB</th><th className="ph-hide">by</th><th /></tr></thead>
            <tbody>{list.data.map((r) => (
              <tr key={r.id}>
                <td><span className="named"><span className="mk">{r.filename.split(".").pop()?.slice(0, 3).toUpperCase()}</span>{r.title}</span><span className="sub">{r.filename}</span></td>
                <td><span className="badge">{r.kind}</span></td><td>{r.month || "—"}</td>
                <td className="r ph-hide">{kb(r.size)}</td><td className="small ph-hide">{r.uploaded_by.replace("user:", "")}</td>
                <td className="r"><div className="row" style={{ justifyContent: "flex-end" }}>
                  <button className="btn sm" onClick={() => download(`/api/kpi/reports/${r.id}/download`, r.filename)}>↓</button>
                  {write && <button className="btn sm danger" onClick={() => api(`/api/kpi/reports/${r.id}`, { method: "DELETE" }).then(list.reload)}>{t("delete")}</button>}
                </div></td>
              </tr>
            ))}</tbody>
          </table></div>
        ) : <Empty />}
      </section>
    </div>
  );
}

export default function Kpi() {
  const { lang } = useContext(LangCtx);
  const s = lang === "uz" ? T.uz : T.ru;
  const { dicts } = usePanel();
  const [view, setView] = useState(() => { try { return localStorage.getItem("hrkit.kpi.view") || "dash"; } catch { return "dash"; } });
  const [month, setMonth] = useState(monthISO());
  const [dept, setDept] = useState("");
  const views = useMemo(() => [["dash", s.dash], ["values", s.values], ["metrics", s.metrics], ["reports", s.reports]], [s]);
  const pick = (v: string) => { setView(v); try { localStorage.setItem("hrkit.kpi.view", v); } catch { /* ignore */ } };
  return (
    <>
      <div className="toolbar" style={{ marginTop: 0 }}>
        <select className="ctl" value={view} onChange={(e) => pick(e.target.value)} aria-label="View">
          {views.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        {(view === "dash" || view === "values") && <>
          <input className="ctl" type="month" value={month} onChange={(e) => setMonth(e.target.value || monthISO())} aria-label={s.month} />
          <select className="ctl" value={dept} onChange={(e) => setDept(e.target.value)} aria-label={s.dept}>
            <option value="">{s.dept}: {s.all}</option>
            {dicts.departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </>}
      </div>
      {view === "dash" && <Dashboard month={month} dept={dept} s={s} />}
      {view === "values" && <Values month={month} dept={dept} s={s} />}
      {view === "metrics" && <Metrics s={s} />}
      {view === "reports" && <Reports s={s} />}
    </>
  );
}
