import { useEffect, useState } from "react";
import { api, auth, money, monthISO, shiftDay, todayISO } from "../api";
import { useT } from "../i18n";
import { Err, Status } from "../ui";

declare global {
  interface Window { Telegram?: { WebApp?: { initData: string; ready: () => void; expand: () => void; colorScheme?: string; HapticFeedback?: { notificationOccurred: (t: string) => void } } } }
}
const tg = () => window.Telegram?.WebApp;
const mini = { mini: true };

export default function MiniApp() {
  const [ready, setReady] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [me, setMe] = useState<any>(null);
  const [tab, setTab] = useState<"me" | "report" | "month">("me");
  const t = useT();

  const loadMe = () => api<any>("/api/miniapp/me", mini).then((m) => {
    setMe(m);
    if ((m.is_lead || ["hr_head", "owner"].includes(m.role)) && tab === "me" && !m.linked) setTab("report");
  });

  useEffect(() => {
    const w = tg();
    w?.ready(); w?.expand();
    if (w?.colorScheme) document.documentElement.dataset.theme = w.colorScheme;
    api<{ token: string }>("/api/miniapp/auth", { body: { init_data: w?.initData || "" }, mini: true })
      .then((r) => { auth.mini = r.token; return loadMe(); })
      .then(() => setReady(true))
      .catch((e) => setErr(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (err) return <div className="mini"><h1>HR</h1><div className="error" style={{ marginTop: 12 }}>{err}</div></div>;
  if (!ready || !me) return <div className="mini muted">Loading…</div>;
  const lead = me.is_lead || ["hr_head", "owner"].includes(me.role);
  if (!me.linked && !lead) return <div className="mini"><LinkFlow onDone={loadMe} /></div>;

  return (
    <div className="mini">
      {tab === "me" && me.linked && <MeView me={me} reload={loadMe} />}
      {tab === "report" && lead && <LeadReport />}
      {tab === "month" && lead && <LeadMonth />}
      {lead && (
        <nav className="mini-tabs">
          {me.linked && <button className={tab === "me" ? "active" : ""} onClick={() => setTab("me")}>{t("me")}</button>}
          <button className={tab === "report" ? "active" : ""} onClick={() => setTab("report")}>{t("report")}</button>
          <button className={tab === "month" ? "active" : ""} onClick={() => setTab("month")}>{t("month")}</button>
        </nav>
      )}
    </div>
  );
}

function Toast({ text }: { text: string | null }) {
  return text ? <div className="toast" role="status">{text}</div> : null;
}
function useToast() {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => { if (!text) return; const id = setTimeout(() => setText(null), 2200); return () => clearTimeout(id); }, [text]);
  return [text, setText] as const;
}

/* ---------- first-time link: branch -> name -> last 4 phone digits ---------- */
function LinkFlow({ onDone }: { onDone: () => void }) {
  const [branches, setBranches] = useState<any[]>([]);
  const [branch, setBranch] = useState<any>(null);
  const [people, setPeople] = useState<any[]>([]);
  const [person, setPerson] = useState<any>(null);
  const [q, setQ] = useState("");
  const [digits, setDigits] = useState("");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api<any[]>("/api/miniapp/link/branches", mini).then(setBranches).catch((e) => setErr(e.message)); }, []);
  useEffect(() => { if (branch) api<any[]>(`/api/miniapp/link/people?branch_id=${branch.id}`, mini).then(setPeople).catch((e) => setErr(e.message)); }, [branch]);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <h1>Find yourself</h1>
      <p className="muted" style={{ margin: 0 }}>Once: choose your branch, then your name. Your Telegram is linked to your card.</p>
      <Err e={err} />
      {!branch && branches.map((b) => <button key={b.id} className="person" style={{ textAlign: "left", cursor: "pointer" }} onClick={() => setBranch(b)}><b>{b.name}</b><span className="muted small">{b.city}</span></button>)}
      {branch && !person && <>
        <div className="row"><button className="btn sm" onClick={() => setBranch(null)}>←</button><b>{branch.name}</b></div>
        <input placeholder="Search name…" value={q} onChange={(e) => setQ(e.target.value)} />
        {people.filter((p) => p.full_name.toLowerCase().includes(q.toLowerCase())).map((p) => (
          <button key={p.id} className="person" style={{ textAlign: "left", cursor: "pointer" }} onClick={() => setPerson(p)}><b>{p.full_name}</b></button>
        ))}
        {people.length === 0 && <div className="muted">Nobody to link here — ask HR.</div>}
      </>}
      {person && (
        <form className="stack" onSubmit={async (e) => {
          e.preventDefault();
          try { await api("/api/miniapp/link", { body: { employee_id: person.id, phone_last4: digits }, mini: true }); onDone(); }
          catch (x: any) { setErr(x.message); }
        }}>
          <div className="row"><button type="button" className="btn sm" onClick={() => setPerson(null)}>←</button><b>{person.full_name}</b></div>
          <label className="field">Last 4 digits of your phone<input inputMode="numeric" pattern="\d{4}" maxLength={4} value={digits} onChange={(e) => setDigits(e.target.value.replace(/\D/g, ""))} /></label>
          <button className="btn primary" disabled={digits.length !== 4}>Link my Telegram</button>
        </form>
      )}
    </div>
  );
}

/* ---------- employee: Keldim / Ketdim ---------- */
function MeView({ me, reload }: { me: any; reload: () => void }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useToast();
  const d = me.today;
  const check = async (kind: "in" | "out") => {
    setBusy(true);
    try {
      const r = await api<any>("/api/miniapp/check", { body: { kind }, mini: true });
      tg()?.HapticFeedback?.notificationOccurred("success");
      setToast(`${kind === "in" ? t("checkIn") : t("checkOut")} · ${String(r.ts).slice(11, 16)}`);
      reload();
    } catch (x: any) { setToast(x.message); } finally { setBusy(false); }
  };
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div>
        <h1>{me.full_name}</h1>
        <div className="muted">{me.position} · {me.branch}</div>
      </div>
      <div className="big-actions">
        <button className="big-btn in" disabled={busy} onClick={() => check("in")}>{t("checkIn")}</button>
        <button className="big-btn out" disabled={busy} onClick={() => check("out")}>{t("checkOut")}</button>
      </div>
      {me.open_shift_from_yesterday && <div className="note">Your shift from yesterday is still open — press “{t("checkOut")}” when you leave.</div>}
      <div className="card stack" style={{ gap: 6 }}>
        <div className="row"><b>{t("today")}</b><span className="spacer" /><Status s={d.status} /></div>
        <div className="row small"><span className="muted">In</span><span className="mono">{d.check_in?.slice(11) || "—"}</span>
          <span className="muted">Out</span><span className="mono">{d.check_out?.slice(11) || "—"}</span>
          <span className="muted">Hours</span><span className="mono">{d.worked_hours ?? "—"}</span></div>
        {d.late_min > 0 && <div className="small" style={{ color: "var(--warn)" }}>Late {d.late_min} min</div>}
      </div>
      {me.month && <div className="grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
        <div className="card tile"><div className="label">Hours</div><div className="value" style={{ fontSize: 20 }}>{me.month.worked_hours}</div></div>
        <div className="card tile"><div className="label">Days</div><div className="value" style={{ fontSize: 20 }}>{me.month.worked_days}</div></div>
        <div className="card tile"><div className="label">Late</div><div className="value" style={{ fontSize: 20 }}>{me.month.late_days}</div></div>
      </div>}
      <Toast text={toast} />
    </div>
  );
}

/* ---------- team lead: daily report ---------- */
function useBranches() {
  const [branches, setBranches] = useState<any[]>([]);
  const [branch, setBranchState] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api<any[]>("/api/miniapp/lead/branches", mini).then((b) => {
      setBranches(b);
      let saved: number | null = null;
      try { saved = Number(localStorage.getItem("hrkit.leadBranch")) || null; } catch { /* ignore */ }
      setBranchState(b.find((x) => x.id === saved)?.id ?? b[0]?.id ?? null);
    }).catch((e) => setErr(e.message));
  }, []);
  const setBranch = (id: number) => { setBranchState(id); try { localStorage.setItem("hrkit.leadBranch", String(id)); } catch { /* ignore */ } };
  return { branches, branch, setBranch, err };
}

function BranchPills({ branches, branch, setBranch }: { branches: any[]; branch: number | null; setBranch: (id: number) => void }) {
  if (branches.length < 2) return <h1>{branches[0]?.name || ""}</h1>;
  return <div className="pills">{branches.map((b) => <button key={b.id} className={`pill ${b.id === branch ? "active" : ""}`} onClick={() => setBranch(b.id)}>{b.name}</button>)}</div>;
}

function LeadReport() {
  const t = useT();
  const { branches, branch, setBranch, err } = useBranches();
  const [day, setDay] = useState(todayISO());
  const [mode, setMode] = useState<"today" | "yesterday" | "other">("today");
  const [data, setData] = useState<any>(null);
  const [state, setState] = useState<Record<number, string>>({});
  const [hours, setHours] = useState<Record<number, number>>({});
  const [q, setQ] = useState("");
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [e2, setE2] = useState<string | null>(null);
  const load = () => branch && api<any>(`/api/miniapp/lead/report?branch_id=${branch}&day=${day}`, mini).then((d) => {
    setData(d);
    setHours(Object.fromEntries(d.rows.map((r: any) => [r.employee_id, r.worked_hours ?? (r.planned_hours || 8)])));
  }).catch((x) => setE2(x.message));
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [branch, day]);

  const save = async (r: any, status: string, h?: number) => {
    setState((s) => ({ ...s, [r.employee_id]: t("saving") }));
    try {
      await api("/api/miniapp/lead/report", { body: { employee_id: r.employee_id, day, status, hours: status === "came" ? (h ?? hours[r.employee_id]) : null }, mini: true });
      setState((s) => ({ ...s, [r.employee_id]: t("saved") }));
      load();
    } catch (x: any) {
      setState((s) => ({ ...s, [r.employee_id]: "⚠ " + (x.status === 409 ? "Someone just changed this — tap again" : x.message) }));
    }
  };
  const rows = (data?.rows || []).filter((r: any) => !q || r.full_name.toLowerCase().includes(q.toLowerCase()));
  const tiles = data ? [["Keldi", data.came], ["Kelmadi", data.absent], ["Not marked", data.unmarked], ["Late", data.late]] : [];

  return (
    <div className="stack" style={{ gap: 12 }}>
      <BranchPills branches={branches} branch={branch} setBranch={setBranch} />
      <Err e={err || e2} />
      <div className="pills">
        <button className={`pill ${mode === "today" ? "active" : ""}`} onClick={() => { setMode("today"); setDay(todayISO()); }}>{t("today")}</button>
        <button className={`pill ${mode === "yesterday" ? "active" : ""}`} onClick={() => { setMode("yesterday"); setDay(shiftDay(todayISO(), -1)); }}>{t("yesterday")}</button>
        <button className={`pill ${mode === "other" ? "active" : ""}`} onClick={() => setMode("other")}>{t("otherDay")}</button>
        {mode === "other" && <input type="date" value={day} max={todayISO()} onChange={(e) => setDay(e.target.value)} />}
      </div>
      {data && <div className="grid" style={{ gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
        {tiles.map(([l, v]) => <div key={l} className="card" style={{ padding: 10, textAlign: "center" }}><div className="num" style={{ fontSize: 20, fontWeight: 800 }}>{v}</div><div className="muted small">{l}</div></div>)}
      </div>}
      {data?.locked && <div className="note">Month is closed — view only.</div>}
      {(data?.rows.length || 0) > 15 && <input placeholder="Search name…" value={q} onChange={(e) => setQ(e.target.value)} />}
      {rows.map((r: any) => {
        const byLead = r.source === "lead";
        const came = byLead && ["present", "late"].includes(r.status);
        const absent = byLead && r.status === "absent";
        const locked = data.locked || r.source === "hr" || r.source === "leave";
        const h = hours[r.employee_id] ?? 8;
        const setH = (v: number) => setHours((x) => ({ ...x, [r.employee_id]: Math.min(24, Math.max(0.5, v)) }));
        return (
          <div key={r.employee_id} className={`person ${byLead ? "done" : ""}`}>
            <div className="top">
              <div style={{ flex: 1 }}>
                <b>{r.full_name}</b>
                <div className="muted small">{r.position}{r.check_in ? ` · in ${r.check_in.slice(11)}` : " · no self check-in"}
                  {r.late_min ? ` · late ${r.late_min}m` : ""}{r.warnings_month ? ` · ⚠ ${r.warnings_month} warnings` : ""}</div>
              </div>
              <Status s={r.status} />
            </div>
            {locked ? <div className="muted small">{r.source === "hr" ? "HR corrected" : r.source === "leave" ? `On ${r.leave_kind}` : "Closed"}</div>
              : r.status === "off" && !expanded[r.employee_id] ? <div className="row small"><span className="muted">Rest day by schedule</span><span className="spacer" />
                <button className="btn sm" onClick={() => setExpanded((x) => ({ ...x, [r.employee_id]: true }))}>Mark anyway</button></div> : <>
              {r.pay_type === "daily" ? (
                <div className="seg" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                  <button className={came && r.worked_hours >= (r.planned_hours || 8) ? "on-came" : ""} onClick={() => save(r, "came", r.planned_hours || 8)}>{t("fullDay")}</button>
                  <button className={came && r.worked_hours < (r.planned_hours || 8) ? "on-came" : ""} onClick={() => save(r, "came", (r.planned_hours || 8) / 2)}>{t("halfDay")}</button>
                  <button className={absent ? "on-absent" : ""} onClick={() => save(r, "absent")}>{t("absent")}</button>
                </div>
              ) : <>
                <div className="seg">
                  <button className={came ? "on-came" : ""} onClick={() => save(r, "came")}>{t("came")}</button>
                  <button className={absent ? "on-absent" : ""} onClick={() => save(r, "absent")}>{t("absent")}</button>
                </div>
                <div className="hours">
                  <button className="btn sm" onClick={() => setH(h - 0.5)}>−</button>
                  <span className="val">{h} h</span>
                  <button className="btn sm" onClick={() => setH(h + 0.5)}>+</button>
                  {[8, 12, 24].map((v) => <button key={v} className={`pill ${h === v ? "active" : ""}`} onClick={() => setH(v)}>{v}</button>)}
                  {came && h !== r.worked_hours && <button className="btn sm primary" onClick={() => save(r, "came")}>{t("save")}</button>}
                </div>
              </>}
              <div className="row small">
                {byLead && <button className="btn sm ghost" onClick={() => save(r, "cancel")}>{t("undo")}</button>}
                <span className="spacer" /><span className="muted">{state[r.employee_id] || ""}</span>
              </div>
            </>}
          </div>
        );
      })}
      {data && rows.length === 0 && <div className="muted">Nobody in this branch.</div>}
    </div>
  );
}

/* ---------- team lead: month + person page ---------- */
function LeadMonth() {
  const t = useT();
  const { branches, branch, setBranch, err } = useBranches();
  const [month, setMonth] = useState(monthISO());
  const [data, setData] = useState<any>(null);
  const [person, setPerson] = useState<any>(null);
  const [e2, setE2] = useState<string | null>(null);
  const load = () => branch && api<any>(`/api/miniapp/lead/month?branch_id=${branch}&month=${month}`, mini).then(setData).catch((x) => setE2(x.message));
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [branch, month]);
  if (person) return <PersonPage row={person} month={month} official={data?.status === "approved" || data?.status === "paid" || data?.status === "closed"}
    onBack={() => { setPerson(null); load(); }} />;
  const months = [0, 1, 2].map((i) => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - i); return d.toISOString().slice(0, 7); });
  const sum = (k: string) => (data?.rows || []).reduce((a: number, r: any) => a + (r[k] || 0), 0);
  return (
    <div className="stack" style={{ gap: 12 }}>
      <BranchPills branches={branches} branch={branch} setBranch={setBranch} />
      <Err e={err || e2} />
      <div className="pills">{months.map((m) => <button key={m} className={`pill ${m === month ? "active" : ""}`} onClick={() => setMonth(m)}>{m}</button>)}</div>
      {data && <div className="card stack" style={{ gap: 4 }}>
        <div className="muted small">On hand</div>
        <div className="num" style={{ fontSize: 26, fontWeight: 800 }}>{money(data.fund)} <span className="small muted">UZS</span></div>
        <span className={`badge ${["approved", "paid", "closed"].includes(data.status) ? "b-ok" : "b-warn"}`}>{["approved", "paid", "closed"].includes(data.status) ? "Official" : "Estimate — HR approves at month end"}</span>
        <div className="row small muted">bonus {money(sum("bonus"))} · advance {money(sum("advance"))} · penalty {money(sum("penalty"))}</div>
        {data.unknown_salary > 0 && <div className="small" style={{ color: "var(--warn)" }}>Salary unknown for {data.unknown_salary} person(s) — not in total</div>}
      </div>}
      {data?.rows.map((r: any) => (
        <button key={r.employee_id} className="person" style={{ textAlign: "left", cursor: "pointer" }} onClick={() => setPerson(r)}>
          <div className="top"><div style={{ flex: 1 }}><b>{r.full_name}</b><div className="muted small">{r.position} · {r.worked_hours}/{r.norm_hours} h</div></div>
            <div className="num" style={{ fontWeight: 800 }}>{money(r.total)}</div></div>
          <div className="row small muted">{t("advance")} {money(r.advance)} · {t("penalty")} {money(r.penalty)}{r.warnings ? ` · ⚠ ${r.warnings}` : ""}</div>
        </button>
      ))}
    </div>
  );
}

const KINDS: { kind: string; key: string; money: boolean }[] = [
  { kind: "advance", key: "advance", money: true }, { kind: "penalty", key: "penalty", money: true },
  { kind: "bonus", key: "bonus", money: true }, { kind: "warning", key: "warning", money: false },
];

function PersonPage({ row, month, official, onBack }: { row: any; month: string; official: boolean; onBack: () => void }) {
  const t = useT();
  const [kind, setKind] = useState<typeof KINDS[number] | null>(null);
  const [step, setStep] = useState<1 | 2>(1);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useToast();
  const lines: [string, unknown][] = [["Hours / norm", `${row.worked_hours} / ${row.norm_hours}`], ["Salary (contract)", money(row.base)], ["Accrued", money(row.accrued)],
    ["Bonus", money(row.bonus)], ["KPI bonus", money(row.kpi)], ["Sales bonus", money(row.sales_bonus)], ["Allowances", money(row.allowances)],
    ["Advance", money(row.advance)], ["Penalty", money(row.penalty)], ["Late penalty (auto)", money(row.late_penalty)], ["Other deductions", money(row.other)]];
  const reset = () => { setKind(null); setStep(1); setAmount(""); setReason(""); setErr(null); };
  return (
    <div className="stack" style={{ gap: 12 }}>
      <div className="row"><button className="btn sm" onClick={onBack}>←</button><b>{row.full_name}</b></div>
      <div className="card" style={{ textAlign: "center" }}>
        <div className="muted small">On hand · {month}</div>
        <div className="num" style={{ fontSize: 32, fontWeight: 800 }}>{money(row.total)}</div>
        <span className={`badge ${official ? "b-ok" : "b-warn"}`}>{official ? "Official" : "Estimate"}</span>
      </div>
      <div className="card stack" style={{ gap: 4 }}>
        {lines.map(([k, v]) => <div key={k} className="row small"><span className="muted">{k}</span><span className="spacer" /><span className="mono">{String(v)}</span></div>)}
      </div>
      {!kind ? (
        <div className="actions4">{KINDS.map((k) => <button key={k.kind} onClick={() => setKind(k)}>{t(k.key)}</button>)}</div>
      ) : (
        <div className="card stack">
          <b>{t(kind.key)}</b>
          {step === 1 ? <>
            {kind.money && <label className="field">Amount (UZS)<input inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value.replace(/\D/g, ""))} /></label>}
            <label className="field">{t("reason")}<textarea rows={2} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
            <div className="row"><button className="btn" onClick={reset}>{t("cancel")}</button><span className="spacer" />
              <button className="btn primary" disabled={reason.trim().length < 3 || (kind.money && !Number(amount))} onClick={() => setStep(2)}>Next</button></div>
          </> : <>
            <div>{kind.money ? <b className="num">{money(Number(amount))} UZS </b> : null}{t(kind.key).toLowerCase()} — {t("confirm").toLowerCase()}?</div>
            <div className="muted small">{reason}</div>
            <Err e={err} />
            <div className="row"><button className="btn" onClick={() => setStep(1)}>←</button><span className="spacer" />
              <button className="btn primary" onClick={async () => {
                try {
                  await api("/api/miniapp/lead/entries", { body: { employee_id: row.employee_id, kind: kind.kind, amount: kind.money ? Number(amount) : 0, reason }, mini: true });
                  setToast(t("saved")); reset();
                } catch (x: any) { setErr(x.message); }
              }}>{t("confirm")}</button></div>
          </>}
        </div>
      )}
      <Toast text={toast} />
    </div>
  );
}
