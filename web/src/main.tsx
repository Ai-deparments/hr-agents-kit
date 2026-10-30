import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import { Lang, LangCtx } from "./i18n";
import MiniApp from "./miniapp/MiniApp";
import Panel from "./panel/Panel";
import Jobs from "./Jobs";
import RaufMini from "./rauf/RaufMini";
import RaufPanel from "./rauf/RaufPanel";
import "./pitaka.css";
import "./styles.css";
import "./dice.css";

function Root() {
  const [lang, setLangState] = useState<Lang>(() => {
    try { return (localStorage.getItem("hrkit.lang") as Lang) || "uz"; } catch { return "uz"; }
  });
  const setLang = (l: Lang) => {
    setLangState(l);
    try { localStorage.setItem("hrkit.lang", l); } catch { /* ignore */ }
  };
  useEffect(() => {
    api("/api/config/public").then((c) => {
      // Pitaka look: primary is ink, the single accent lives in pitaka.css — branding only names the app
      document.title = c?.branding?.short || "HR";
      let stored: string | null = null;
      try { stored = localStorage.getItem("hrkit.lang"); } catch { /* ignore */ }
      if (!stored && c?.company?.default_language) setLangState(c.company.default_language);
    }).catch(() => {});
  }, []);
  const p = location.pathname;
  const isMini = p === "/m" || p.startsWith("/m/");
  return (
    <LangCtx.Provider value={{ lang, setLang }}>
      {p === "/jobs" || p.startsWith("/jobs/") ? <Jobs /> : p.startsWith("/m/rauf") ? <RaufMini /> : isMini ? <MiniApp /> : p.startsWith("/rauf") ? <RaufPanel /> : <Panel />}
    </LangCtx.Provider>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><Root /></StrictMode>);
