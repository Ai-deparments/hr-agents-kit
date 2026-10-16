import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { Lang, LangCtx } from "./i18n";
import MiniApp from "./miniapp/MiniApp";
import Panel from "./panel/Panel";
import "./styles.css";

function Root() {
  const [lang, setLangState] = useState<Lang>(() => {
    try { return (localStorage.getItem("hrkit.lang") as Lang) || "en"; } catch { return "en"; }
  });
  const setLang = (l: Lang) => {
    setLangState(l);
    try { localStorage.setItem("hrkit.lang", l); } catch { /* ignore */ }
  };
  useEffect(() => {
    api("/api/config/public").then((c) => {
      const color = c?.branding?.primary_color;
      if (color) document.documentElement.style.setProperty("--primary", color);
      if (c?.branding?.accent_color) document.documentElement.style.setProperty("--accent", c.branding.accent_color);
      document.title = c?.branding?.short || "HR";
      let stored: string | null = null;
      try { stored = localStorage.getItem("hrkit.lang"); } catch { /* ignore */ }
      if (!stored && c?.company?.default_language) setLangState(c.company.default_language);
    }).catch(() => {});
  }, []);
  const isMini = location.pathname === "/m" || location.pathname.startsWith("/m/");
  return (
    <LangCtx.Provider value={{ lang, setLang }}>
      {isMini ? <MiniApp /> : <Panel />}
    </LangCtx.Provider>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><Root /></StrictMode>);
