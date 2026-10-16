import { useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";

export default function Login({ onLogin }: { onLogin: (token: string) => void }) {
  const t = useT();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="login">
      <form className="card stack" onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try { onLogin((await api<{ token: string }>("/api/auth/login", { body: { username: u, password: p } })).token); }
        catch (x: any) { setErr(x.message); } finally { setBusy(false); }
      }}>
        <div className="brand" style={{ padding: 0 }}><span className="brand-mark">HR</span><span>{document.title}</span></div>
        <p className="muted" style={{ margin: 0 }}>HR panel for office, HR, payroll and regional managers.</p>
        <label className="field">{t("username")}<input autoFocus value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" /></label>
        <label className="field">{t("password")}<input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></label>
        {err && <div className="error">{err}</div>}
        <button className="btn primary" disabled={busy || !u || !p}>{t("login")}</button>
      </form>
    </div>
  );
}
