import { Fragment, ReactNode, useEffect, useRef, useState } from "react";
import { Bot, SendHorizontal } from "lucide-react";
import { api } from "../api";

type Msg = { role: "user" | "assistant"; text: string };

/** **bold** inside a line -> <b>; no HTML is ever injected. */
function inline(s: string): ReactNode[] {
  return s.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith("**") && p.endsWith("**") ? <b key={i}>{p.slice(2, -2)}</b> : <Fragment key={i}>{p}</Fragment>));
}

/** The agent answers in light Markdown: headings, bullets, tables, bold. */
function Md({ text }: { text: string }) {
  const out: ReactNode[] = [];
  const lines = text.replace(/<[^>]+>/g, "").split("\n");
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (/^\s*\|/.test(l)) {
      const rows: string[][] = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) {
        if (!/^\s*\|[\s:|-]+\|\s*$/.test(lines[i])) rows.push(lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
        i++;
      }
      i--;
      out.push(<table key={i} className="tbl md-t"><tbody>{rows.map((r, k) => (
        <tr key={k}>{r.map((c, j) => (k === 0 ? <th key={j}>{inline(c)}</th> : <td key={j}>{inline(c)}</td>))}</tr>))}</tbody></table>);
    } else if (/^#{1,4}\s/.test(l)) out.push(<div key={i} className="md-h">{inline(l.replace(/^#+\s/, ""))}</div>);
    else if (/^\s*[-•*]\s/.test(l)) out.push(<div key={i} className="md-li">{inline(l.replace(/^\s*[-•*]\s/, ""))}</div>);
    else if (l.trim()) out.push(<div key={i}>{inline(l)}</div>);
    else out.push(<div key={i} className="md-sp" />);
  }
  return <>{out}</>;
}

const HINTS = {
  uz: ["Bugun kim kech qoldi?", "Sinov muddatini olib tashla: ", "Shu oy oyligini hisobla: "],
  ru: ["Кто сегодня опоздал?", "Убери испытательный срок у ", "Посчитай зарплату за месяц: "],
};

/** HR agent chat on the dashboard: same agent and tools as the Telegram bot. */
export default function AgentBox({ lang }: { lang: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { box.current?.scrollTo(0, box.current.scrollHeight); }, [msgs.length, busy]);
  const uz = lang === "uz";

  const send = async (q: string) => {
    if (!q.trim() || busy) return;
    setMsgs((m) => [...m, { role: "user", text: q }]);
    setText("");
    setBusy(true);
    try {
      const r = await api<{ answer: string }>("/api/agents/hr/chat", { body: { text: q } });
      setMsgs((m) => [...m, { role: "assistant", text: r.answer }]);
    } catch (x: any) {
      setMsgs((m) => [...m, { role: "assistant", text: x.message }]);
    } finally { setBusy(false); input.current?.focus(); }
  };

  return (
    <section className="card agent-box">
      <div className="card-h"><span className="card-t"><Bot className="ic inl" size={16} aria-hidden="true" /> {uz ? "HR agent" : "HR-агент"}</span>
        <span className="card-s">{uz ? "Botdagi agentning o'zi: savol bering yoki topshiriq yozing" : "Тот же агент, что в боте: спросите или поручите"}</span></div>
      {msgs.length > 0 && (
        <div className="ab-msgs" ref={box}>
          {msgs.map((m, i) => <div key={i} className={`ab-msg ${m.role}`}>{m.role === "assistant" ? <Md text={m.text} /> : m.text}</div>)}
          {busy && <div className="ab-msg assistant muted">…</div>}
        </div>
      )}
      <form className="ab-form" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <input ref={input} value={text} onChange={(e) => setText(e.target.value)} disabled={busy}
          placeholder={uz ? "Masalan: Ali Valiyevning sinov muddatini olib tashla" : "Например: убери испытательный срок у Али Валиева"} />
        <button className="btn primary" disabled={busy || !text.trim()} aria-label={uz ? "Yuborish" : "Отправить"}>
          <SendHorizontal size={16} aria-hidden="true" /></button>
      </form>
      {msgs.length === 0 && (
        <div className="ab-hints">{HINTS[uz ? "uz" : "ru"].map((h) => (
          <button key={h} type="button" className="pill" onClick={() => (h.endsWith(" ") ? (setText(h), input.current?.focus()) : send(h))}>{h.trim()}</button>
        ))}</div>
      )}
    </section>
  );
}
