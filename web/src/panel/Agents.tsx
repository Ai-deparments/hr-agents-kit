import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import { Empty, Err, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

type Msg = { role: "user" | "assistant"; text: string };

export function AgentChat() {
  const t = useT();
  const { data, error } = useLoad<any>("/api/agents");
  const [agent, setAgent] = useState("hamza");
  const [msgs, setMsgs] = useState<Record<string, Msg[]>>({});
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const list = (data?.agents || []).filter((a: any) => a.name !== "suhayl");
  const cur = list.find((a: any) => a.name === agent);
  const history = msgs[agent] || [];
  useEffect(() => { box.current?.scrollTo(0, box.current.scrollHeight); }, [history.length, busy]);

  const send = async (q: string) => {
    if (!q.trim()) return;
    setMsgs((m) => ({ ...m, [agent]: [...(m[agent] || []), { role: "user", text: q }] }));
    setText("");
    setBusy(true);
    try {
      const r = await api<any>(`/api/agents/${agent}/chat`, { body: { text: q } });
      setMsgs((m) => ({ ...m, [agent]: [...(m[agent] || []), { role: "assistant", text: r.answer }] }));
    } catch (x: any) {
      setMsgs((m) => ({ ...m, [agent]: [...(m[agent] || []), { role: "assistant", text: "⚠️ " + x.message }] }));
    } finally { setBusy(false); }
  };

  return (
    <div className="grid agent-grid">
      <div className="card stack" style={{ gap: 6 }}>
        <Err e={error} />
        {data && <span className={`badge ${data.llm ? "b-ok" : "b-warn"}`}>{data.llm ? "Claude: on" : "Offline: commands only"}</span>}
        {list.map((a: any) => (
          <button key={a.name} className={`btn ${a.name === agent ? "primary" : ""}`} style={{ textAlign: "left" }} onClick={() => setAgent(a.name)}>
            <div style={{ textTransform: "capitalize" }}>{a.name}</div><div className="small" style={{ opacity: .75, fontWeight: 500 }}>{a.title}</div>
          </button>
        ))}
        <p className="muted small" style={{ margin: 0 }}>Suhayl talks only to employees about their own data — use Telegram.</p>
      </div>
      <div className="card chat">
        <div className="row" style={{ marginBottom: 8 }}>
          {cur?.commands.map((c: string) => <button key={c} className="pill" onClick={() => send(c)}>{c}</button>)}
        </div>
        <div className="msgs" ref={box}>
          {history.length === 0 && <Empty text="Ask in plain words, e.g. “who was late today?”" />}
          {history.map((m, i) => <div key={i} className={`msg ${m.role}`}>{m.text}</div>)}
          {busy && <div className="msg assistant muted">…</div>}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder={`Message ${agent}…`} />
          <button className="btn primary" disabled={busy || !text.trim()}>{t("send")}</button>
        </form>
      </div>
    </div>
  );
}

export function Knowledge() {
  const { me, dicts } = usePanel();
  const [q, setQ] = useState("");
  const { data, error, reload } = useLoad<any[]>(`/api/sops?q=${encodeURIComponent(q)}`, []);
  const [pos, setPos] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="note">One SOP library for every agent and the panel. Agents quote it and never invent rule text.</div>
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <input placeholder="Search rules…" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: "1 1 200px" }} />
          {can(me, "hr.write") && <>
            <select value={pos} onChange={(e) => setPos(e.target.value)}><option value="">All positions</option>{dicts.positions.map((p) => <option key={p.code} value={p.code}>{p.title}</option>)}</select>
            <label className="btn primary">Upload .md / .txt<input type="file" accept=".md,.txt" hidden onChange={async (e) => {
              const f = e.target.files?.[0]; if (!f) return;
              const fd = new FormData(); fd.append("file", f);
              try { const r = await api<any>(`/api/sops/upload${pos ? `?position_code=${pos}` : ""}`, { form: fd }); setMsg(`Created ${r.created} SOP(s). Each “# Title” section becomes one SOP.`); reload(); }
              catch (x: any) { setMsg(x.message); }
              e.target.value = "";
            }} /></label>
          </>}
        </div>
        {msg && <div className="note" style={{ marginBottom: 10 }}>{msg}</div>}
        <Err e={error} />
        <div className="stack">
          {data?.map((s) => (
            <div key={s.id} className="person"><div className="row"><b>{s.title}</b><span className="badge">{s.position || "all"}</span></div>
              <div className="small muted" style={{ whiteSpace: "pre-wrap" }}>{s.excerpt}</div></div>
          ))}
        </div>
        {data?.length === 0 && <Empty />}
      </div>
    </div>
  );
}

export function Chats() {
  const [agent, setAgent] = useState("");
  const [q, setQ] = useState("");
  const { data, error } = useLoad<any[]>(`/api/chats?${agent ? `agent=${agent}&` : ""}q=${encodeURIComponent(q)}`, []);
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 12 }}>
        <select value={agent} onChange={(e) => setAgent(e.target.value)}><option value="">All agents</option>
          {["hamza", "ozoda", "bexruz", "husayn", "suhayl", "rauf", "reklama"].map((a) => <option key={a}>{a}</option>)}</select>
        <input placeholder="Search text…" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: "1 1 200px" }} />
      </div>
      <Err e={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>When</th><th>Agent</th><th>User</th><th>Role</th><th>Text</th></tr></thead>
        <tbody>{data?.map((m) => (
          <tr key={m.id}><td className="mono small">{String(m.ts).slice(0, 16).replace("T", " ")}</td><td>{m.agent}</td><td className="small">{m.user_key}</td>
            <td><span className={`badge ${m.role === "user" ? "" : "b-info"}`}>{m.role}</span></td><td className="small" style={{ whiteSpace: "pre-wrap", maxWidth: 520 }}>{m.text}</td></tr>
        ))}</tbody>
      </table></div>
      {data?.length === 0 && <Empty />}
    </div>
  );
}

export function Audit() {
  const { data, error } = useLoad<any[]>("/api/audit?limit=300");
  return (
    <div className="card">
      <Err e={error} />
      <div className="table-wrap"><table>
        <thead><tr><th>When</th><th>Actor</th><th>Role</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
        <tbody>{data?.map((a) => (
          <tr key={a.id}><td className="mono small">{String(a.ts).slice(0, 19).replace("T", " ")}</td><td className="small">{a.actor}</td><td className="small">{a.role}</td>
            <td><span className="badge">{a.action}</span></td><td className="small">{a.target || "—"}</td>
            <td className="mono small" style={{ maxWidth: 380, wordBreak: "break-word" }}>{JSON.stringify(a.details)}</td></tr>
        ))}</tbody>
      </table></div>
    </div>
  );
}
