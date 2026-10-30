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
import { Audit, Chats, Knowledge } from "./Agents";
import Registrations from "./Registrations";
import Structure from "./Structure";
import Roles from "./Roles";
import Broadcast from "./Broadcast";
import Kpi from "./Kpi";
import HhSearch from "./HhSearch";
import Materials from "./Materials";
import Camera from "./Camera";
import { BotAccess, PendingUsers, UsersPage } from "./Users";
import { Ic } from "../icons";

type Page = { key: string; sec: string; icon: string; perm: string | null; el: () => JSX.Element };

const PAGES: Page[] = [
  { key: "dashboard", sec: "secMain", icon: "home", perm: "hr.read", el: () => <Dashboard /> },
  { key: "analytics", sec: "secMain", icon: "chart", perm: "hr.read", el: () => <Analytics /> },
  { key: "chats", sec: "secAgent", icon: "chat", perm: "hr.read", el: () => <Chats /> },
  { key: "employees", sec: "secPeople", icon: "team", perm: "hr.read", el: () => <Employees /> },
  { key: "structure", sec: "secPeople", icon: "tree", perm: "hr.read", el: () => <Structure /> },
  { key: "attendance", sec: "secPeople", icon: "clock", perm: "hr.read", el: () => <Attendance /> },
  { key: "camera", sec: "secPeople", icon: "camera", perm: "hr.read", el: () => <Camera /> },
  { key: "tabel", sec: "secPeople", icon: "grid", perm: "hr.read", el: () => <Tabel /> },
  { key: "requests", sec: "secPeople", icon: "file", perm: "hr.read", el: () => <Requests /> },
  { key: "approvals", sec: "secPeople", icon: "check", perm: "hr.read", el: () => <Approvals /> },
  { key: "documents", sec: "secPeople", icon: "folder", perm: "hr.read", el: () => <Documents /> },
  { key: "kpi", sec: "secMoney", icon: "chart", perm: "hr.read", el: () => <Kpi /> },
  { key: "payroll", sec: "secMoney", icon: "wallet", perm: "hr.read", el: () => <Payroll /> },
  { key: "onboarding", sec: "secGrowth", icon: "flag", perm: "hr.read", el: () => <Onboarding /> },
  { key: "materials", sec: "secGrowth", icon: "book", perm: "hr.read", el: () => <Materials /> },
  { key: "broadcast", sec: "secGrowth", icon: "send", perm: "broadcast", el: () => <Broadcast /> },
  { key: "recruiting", sec: "secGrowth", icon: "team", perm: "recruiting.read", el: () => <Recruiting /> },
  { key: "hh", sec: "secGrowth", icon: "search", perm: "hh.search", el: () => <HhSearch /> },
  { key: "engagement", sec: "secGrowth", icon: "heart", perm: "hr.read", el: () => <Engagement /> },
  { key: "users", sec: "secUsers", icon: "team", perm: "*", el: () => <UsersPage /> },
  { key: "pendingUsers", sec: "secUsers", icon: "clock", perm: "*", el: () => <PendingUsers /> },
  { key: "botAccess", sec: "secUsers", icon: "key", perm: "registrations", el: () => <BotAccess /> },
  { key: "registrations", sec: "secBots", icon: "inbox", perm: "registrations", el: () => <Registrations /> },
  { key: "roles", sec: "secAdmin", icon: "shield", perm: "*", el: () => <Roles /> },
  { key: "knowledge", sec: "secAdmin", icon: "book", perm: null, el: () => <Knowledge /> },
  { key: "audit", sec: "secAdmin", icon: "shield", perm: "audit.read", el: () => <Audit /> },
];
const BNAV = ["dashboard", "registrations", "employees", "payroll"];

type Theme = "light" | "dark";
function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, set] = useState<Theme>(() => {
    try { return (localStorage.getItem("pk-theme") as Theme) || "dark"; } catch { return "dark"; }
  });
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  return [theme, (t) => { set(t); try { localStorage.setItem("pk-theme", t); } catch { /* ignore */ } }];
}

export default function Panel() {
  const [token, setToken] = useState(auth.panel);
  const [me, setMe] = useState<Me | null>(null);
  const [dicts, setDicts] = useState<Dicts | null>(null);
  const [page, setPage] = useState(() => {
    try { return localStorage.getItem("hrkit.page") || "dashboard"; } catch { return "dashboard"; }
  });
  const [stuck, setStuck] = useState(false);
  const [theme, setTheme] = useTheme();
  const [more, setMore] = useState(false);
  const [q, setQ] = useState("");
  const [badges, setBadges] = useState<{ registrations: number | null; requests: number | null; approvals: number | null }>(
    { registrations: null, requests: null, approvals: null });
  useEffect(() => {
    if (!me) return;
    const load = () => api("/api/badges").then(setBadges).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => clearInterval(t);
  }, [me, page]);
  const t = useT();
  const { lang, setLang } = useContext(LangCtx);

  useEffect(() => {
    const out = () => { setToken(null); setMe(null); };
    window.addEventListener("hrkit:logout", out);
    return () => window.removeEventListener("hrkit:logout", out);
  }, []);
  useEffect(() => {
    const on = () => setStuck(window.scrollY > 4);
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  useEffect(() => {
    if (!token) return;
    Promise.all([api<Me>("/api/me"), api<Dicts>("/api/dictionaries")])
      .then(([m, d]) => { setMe(m); setDicts(d); })
      .catch(() => { auth.panel = null; setToken(null); });
  }, [token]);

  if (!token) return <Login onLogin={(tk) => { auth.panel = tk; setToken(tk); }} />;
  if (!me || !dicts) return <div className="login-wrap"><div className="login muted">Loading…</div></div>;

  const visible = PAGES.filter((p) => !p.perm || can(me, p.perm));
  const current = visible.find((p) => p.key === page) || visible[0];
  const go = (k: string) => {
    setPage(k); setMore(false); window.scrollTo(0, 0);
    try { localStorage.setItem("hrkit.page", k); } catch { /* ignore */ }
  };
  const logout = () => { auth.panel = null; setToken(null); setMe(null); };
  const reloadDicts = () => api<Dicts>("/api/dictionaries").then(setDicts);
  const sections = [...new Set(visible.map((p) => p.sec))];
  const bnav = visible.filter((p) => BNAV.includes(p.key)).slice(0, 4);
  const navItems = (list: Page[]) => list.map((p) => (
    <button key={p.key} className="nav-i" aria-current={p.key === current?.key ? "page" : undefined} onClick={() => go(p.key)}>
      <Ic n={p.icon} />{t(p.key)}{p.key === "registrations" && (badges.registrations || 0) > 0 && <span className="cnt">{badges.registrations}</span>}</button>
  ));

  return (
    <PanelCtx.Provider value={{ me, dicts, reloadDicts, go }}>
      <div className="app">
        <aside className="side">
          <div className="brand">
            <svg className="brand-cube" viewBox="0 0 34 34" aria-hidden="true">
              <path d="M17 2 31 9.5v15L17 32 3 24.5v-15z" fill="var(--accent)" />
              <path d="M17 2 31 9.5 17 17 3 9.5z" fill="#ff6aa6" opacity=".9" />
              <path d="M17 17v15L3 24.5v-15z" fill="#a3134f" />
            </svg>
            <span className="logo">{document.title.replace(/\s*HR$/i, "") || "HR"}</span>
          </div>
          <nav className="nav">
            {sections.map((s) => (
              <div key={s}>
                <div className="nav-sec">{t(s)}</div>
                {navItems(visible.filter((p) => p.sec === s))}
              </div>
            ))}
          </nav>
          <div className="side-tools">
            {can(me, "*") && <button title={t("roles")} onClick={() => go("roles")}><Ic n="key" /></button>}
            <button title={t("structure")} onClick={() => go("structure")}><Ic n="tree" /></button>
            <button title="Theme" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}><Ic n={theme === "dark" ? "sun" : "moon"} /></button>
            <button title={t("logout")} onClick={logout}><Ic n="out" /></button>
          </div>
        </aside>
        <main className="main">
          <header className={`hdr${stuck ? " stuck" : ""}`}>
            <div className="hdr-1">
              <h1>{current ? t(current.key) : ""}</h1>
              <form className="hsearch" onSubmit={(e) => {
                e.preventDefault();
                const hit = visible.find((p) => t(p.key).toLowerCase().includes(q.trim().toLowerCase()));
                if (hit && q.trim()) { go(hit.key); setQ(""); }
              }}>
                <Ic n="search" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} list="hr-pages" />
                <datalist id="hr-pages">{visible.map((p) => <option key={p.key} value={t(p.key)} />)}</datalist>
              </form>
              {badges.registrations !== null && <button className="hbtn" title={t("registrations")} onClick={() => go("registrations")}>
                <Ic n="inbox" />{badges.registrations > 0 && <span className="cnt">{badges.registrations}</span>}</button>}
              {badges.requests !== null && <button className="hbtn" title={t("requests")} onClick={() => go("requests")}>
                <Ic n="file" />{badges.requests > 0 && <span className="cnt">{badges.requests}</span>}</button>}
              {badges.approvals !== null && <button className="hbtn" title={t("approvals")} onClick={() => go("approvals")}>
                <Ic n="warn" />{badges.approvals > 0 && <span className="cnt">{badges.approvals}</span>}</button>}
              <select className="ctl hlang" value={lang} onChange={(e) => setLang(e.target.value as Lang)} aria-label="Language">
                <option value="uz">O'zbekcha</option><option value="ru">Русский</option><option value="en">English</option>
              </select>
              <span className="named" title={me.role}><span className="avatar" style={{ background: "var(--accent)", color: "#fff" }}>
                {(me.full_name || me.username).slice(0, 1).toUpperCase()}</span></span>
            </div>
          </header>
          <div className="page">
            {current ? current.el() : <div className="empty">No sections available for your role.</div>}
          </div>
        </main>
      </div>
      <nav className="bnav">
        {bnav.map((p) => (
          <a key={p.key} href="#" aria-current={p.key === current?.key && !more ? "page" : undefined}
            onClick={(e) => { e.preventDefault(); go(p.key); }}><Ic n={p.icon} size={18} />{t(p.key)}</a>
        ))}
        <a href="#" aria-current={more ? "page" : undefined} onClick={(e) => { e.preventDefault(); setMore(!more); }}>
          <Ic n="more" size={18} />{t("more")}</a>
      </nav>
      {more && (
        <div className="drawer-overlay" onClick={() => setMore(false)}>
          <div className="sheet" onClick={(e) => e.stopPropagation()}>
            {sections.map((s) => (
              <div key={s}><div className="nav-sec">{t(s)}</div><div className="nav">{navItems(visible.filter((p) => p.sec === s))}</div></div>
            ))}
            <button className="nav-i" onClick={logout}><Ic n="out" />{t("logout")}</button>
          </div>
        </div>
      )}
    </PanelCtx.Provider>
  );
}
