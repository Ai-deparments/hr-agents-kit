// Panel charts on recharts. Colours come from CSS variables (--viz-*, --abc-*), validated for light and dark themes.
import {
  Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

const AXIS = { fill: "var(--muted)", fontSize: 11 };
const n0 = (v: number) => v.toLocaleString("ru-RU", { maximumFractionDigits: 1 });

function Tip({ title, rows }: { title: string; rows: [string, string, string?][] }) {
  return (
    <div className="viz-tip">
      <b>{title}</b>
      {rows.map(([label, value, color]) => (
        <div key={label}>{color && <i style={{ background: color }} />}<span>{label}</span><em>{value}</em></div>
      ))}
    </div>
  );
}

export type AttDay = { day: string; came: number; scheduled: number; late: number };

/** Daily attendance: bars = came, area = planned (one axis: people). */
export function AttendanceChart({ days, lang, labels }: { days: AttDay[]; lang: string; labels: { came: string; plan: string; late: string } }) {
  const dm = (iso: string) => new Date(iso + "T12:00:00").toLocaleDateString(lang === "en" ? "en-GB" : "ru-RU", { day: "2-digit", month: "2-digit" });
  return (
    <div className="viz" role="img" aria-label={`${labels.came} / ${labels.plan}`}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={days} margin={{ top: 8, right: 8, bottom: 0, left: -18 }} barCategoryGap="30%">
          <CartesianGrid vertical={false} stroke="var(--grid)" strokeDasharray="3 4" />
          <XAxis dataKey="day" tickFormatter={dm} tick={AXIS} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={8} />
          <YAxis allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} width={48} />
          <Tooltip cursor={{ fill: "var(--hover)" }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as AttDay;
            const pct = d.scheduled ? ` · ${Math.round((100 * d.came) / d.scheduled)}%` : "";
            return <Tip title={dm(d.day)} rows={[[labels.came, `${d.came}${pct}`, "var(--viz-1)"], [labels.plan, String(d.scheduled), "var(--viz-2)"],
              [labels.late, String(d.late)]]} />;
          }} />
          <Area type="linear" dataKey="scheduled" stroke="var(--viz-2)" strokeWidth={2} fill="var(--viz-2)" fillOpacity={0.12}
            dot={false} activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }} isAnimationActive={false} />
          <Bar dataKey="came" fill="var(--viz-1)" radius={[4, 4, 0, 0]} maxBarSize={28} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export type ParetoRow = { rank: number; employee_id: number; full_name: string; value: number; share: number; cum_share: number; class: "A" | "B" | "C" };

/** Pareto as one % axis: each bar = cumulative share up to this person, coloured by class; dashed A/B cut-offs. */
export function ParetoChart({ rows, a, b, valueLabel }: { rows: ParetoRow[]; a: number; b: number; valueLabel: string }) {
  const fill = { A: "var(--abc-a)", B: "var(--abc-b)", C: "var(--abc-c)" };
  return (
    <div className="viz" role="img" aria-label="Pareto">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -18 }} barCategoryGap={rows.length > 40 ? 1 : "15%"}>
          <CartesianGrid vertical={false} stroke="var(--grid)" strokeDasharray="3 4" />
          <XAxis dataKey="rank" tick={AXIS} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={16} />
          <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickFormatter={(v) => `${v}%`} tick={AXIS} axisLine={false} tickLine={false} width={48} />
          {[[a, "A"], [b, "B"]].map(([y, k]) => (
            <ReferenceLine key={k} y={y as number} stroke="var(--muted)" strokeDasharray="6 4"
              label={{ value: `${k} · ${y}%`, position: "insideTopLeft", fill: "var(--text-2)", fontSize: 11 }} />
          ))}
          <Tooltip cursor={{ fill: "var(--hover)" }} content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const r = payload[0].payload as ParetoRow;
            return <Tip title={`${r.rank}. ${r.full_name}`} rows={[[valueLabel, n0(r.value)], ["%", `${n0(r.share)}%`],
              ["Σ", `${n0(r.cum_share)}%`], ["ABC", r.class, fill[r.class]]]} />;
          }} />
          <Bar dataKey="cum_share" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {rows.map((r) => <Cell key={r.employee_id} fill={fill[r.class]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
