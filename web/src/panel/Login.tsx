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
    <div className="login-wrap">
      <form className="login" onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try { onLogin((await api<{ token: string }>("/api/auth/login", { body: { username: u, password: p } })).token); }
        catch (x: any) { setErr(x.message); } finally { setBusy(false); }
      }}>
        <span className="logo">{document.title}</span>
        <h1>{t("login")}</h1>
        <label>{t("username")}<input autoFocus value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" /></label>
        <label>{t("password")}<input type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></label>
        {err && <div className="login-err">{err}</div>}
        <button className="btn btn-p" disabled={busy || !u || !p}>{t("login")}</button>
      </form>
    </div>
  );
}
