import { useEffect, useState } from "react";
import { api, auth } from "../api";
import { Lang, LangCtx, useT } from "../i18n";
import { useContext } from "react";
import { can, Dicts, Me, PanelCtx } from "./ctx";
import Login from "./Login";
import Dashboard from "./Dashboard";
import Employees from "./Employees";
import { Attendance, Tabel } from "./Attendance";
import Payroll from "./Payroll";
import { Approvals, Requests } from "./Requests";
import { Documents, Onboarding } from "./Onboarding";
import Recruiting from "./Recruiting";
import Analytics from "./Analytics";
import Engagement from "./Engagement";
import { AgentChat, Audit, Chats, Knowledge } from "./Agents";

type Page = { key: string; perm: string | null; el: () => JSX.Element };

const PAGES: Page[] = [
  { key: "dashboard", perm: "hr.read", el: () => <Dashboard /> },
  { key: "employees", perm: "hr.read", el: () => <Employees /> },
  { key: "attendance", perm: "hr.read", el: () => <Attendance /> },
  { key: "tabel", perm: "hr.read", el: () => <Tabel /> },
  { key: "payroll", perm: "hr.read", el: () => <Payroll /> },
  { key: "requests", perm: "hr.read", el: () => <Requests /> },
  { key: "approvals", perm: "hr.read", el: () => <Approvals /> },
  { key: "onboarding", perm: "hr.read", el: () => <Onboarding /> },
  { key: "documents", perm: "hr.read", el: () => <Documents /> },
  { key: "recruiting", perm: "recruiting.read", el: () => <Recruiting /> },
  { key: "analytics", perm: "hr.read", el: () => <Analytics /> },
  { key: "engagement", perm: "hr.read", el: () => <Engagement /> },
  { key: "agents", perm: null, el: () => <AgentChat /> },
  { key: "knowledge", perm: null, el: () => <Knowledge /> },
  { key: "chats", perm: "hr.read", el: () => <Chats /> },
  { key: "audit", perm: "audit.read", el: () => <Audit /> },
];

export default function Panel() {
  const [token, setToken] = useState(auth.panel);
  const [me, setMe] = useState<Me | null>(null);
  const [dicts, setDicts] = useState<Dicts | null>(null);
  const [page, setPage] = useState(() => {
    try { return localStorage.getItem("hrkit.page") || "dashboard"; } catch { return "dashboard"; }
  });
  const t = useT();
  const { lang, setLang } = useContext(LangCtx);

  useEffect(() => {
    const out = () => { setToken(null); setMe(null); };
    window.addEventListener("hrkit:logout", out);
    return () => window.removeEventListener("hrkit:logout", out);
  }, []);
  useEffect(() => {
    if (!token) return;
    Promise.all([api<Me>("/api/me"), api<Dicts>("/api/dictionaries")])
      .then(([m, d]) => { setMe(m); setDicts(d); })
      .catch(() => { auth.panel = null; setToken(null); });
  }, [token]);

  if (!token) return <Login onLogin={(tk) => { auth.panel = tk; setToken(tk); }} />;
  if (!me || !dicts) return <div className="login muted">Loading…</div>;

  const visible = PAGES.filter((p) => !p.perm || can(me, p.perm));
  const current = visible.find((p) => p.key === page) || visible[0];
  const go = (k: string) => { setPage(k); try { localStorage.setItem("hrkit.page", k); } catch { /* ignore */ } };
  const logout = () => { auth.panel = null; setToken(null); setMe(null); };

  return (
    <PanelCtx.Provider value={{ me, dicts }}>
      <div className="shell">
        <aside className="side">
          <div className="brand"><span className="brand-mark">HR</span><span>{document.title}</span></div>
          <nav className="nav">
            {visible.map((p) => (
              <button key={p.key} className={p.key === current?.key ? "active" : ""} onClick={() => go(p.key)}>{t(p.key)}</button>
            ))}
          </nav>
        </aside>
        <main className="main">
          <div className="topbar">
            <select className="mobile-nav" value={current?.key} onChange={(e) => go(e.target.value)} aria-label="Section">
              {visible.map((p) => <option key={p.key} value={p.key}>{t(p.key)}</option>)}
            </select>
            <h1>{current ? t(current.key) : ""}</h1>
            <div className="right">
              <span className="badge">{me.full_name || me.username} · {me.role}{me.branch_scope ? ` · ${me.branch_scope.length} br.` : ""}</span>
              <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} aria-label="Language">
                <option value="en">EN</option><option value="uz">UZ</option><option value="ru">RU</option>
              </select>
              <button className="btn sm" onClick={logout}>{t("logout")}</button>
            </div>
          </div>
          {current ? current.el() : <div className="muted">No sections available for your role.</div>}
        </main>
      </div>
    </PanelCtx.Provider>
  );
}
