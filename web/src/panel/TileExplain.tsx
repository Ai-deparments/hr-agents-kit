import { Database, Sigma } from "lucide-react";
import { Err, Modal, useLoad } from "../ui";

type Explain = {
  title: string; value: string | number; formula: string;
  sources: { name: string; detail: string; updated?: string | null }[];
  groups: { title: string; items: { label: string; value: number }[] }[];
  rows_title?: string; rows: { name: string; info: string; extra: string }[];
  note?: string; avg?: number | null;
};

const num = (v: string | number) => (typeof v === "number" ? v.toLocaleString("ru-RU") : v);

/** Click on a dashboard tile: how the number is built and the rows behind it. */
export default function TileExplain({ tile, onClose }: { tile: string; onClose: () => void }) {
  const { data: x, error } = useLoad<Explain>(`/api/dashboard/explain/${tile}`);
  return (
    <Modal title={x?.title || "…"} onClose={onClose}>
      <Err e={error} />
      {x && (
        <div className="tx">
          <div className="tx-value">{num(x.value)}{x.avg != null && <span className="muted small"> · o'rtacha {num(x.avg)}</span>}</div>
          <div className="tx-sec"><Sigma className="ic inl" size={14} aria-hidden="true" /> <b>Qanday hisoblanadi</b><p>{x.formula}</p></div>
          {x.sources.length > 0 && (
            <div className="tx-sec"><Database className="ic inl" size={14} aria-hidden="true" /> <b>Manba</b>
              <ul className="tx-src">{x.sources.map((s) => (
                <li key={s.name}><b>{s.name}</b> — {s.detail}
                  {s.updated && <span className="muted small"> · oxirgi ma'lumot {s.updated.replace("T", " ")}</span>}</li>
              ))}</ul>
            </div>
          )}
          {x.groups.length > 0 && (
            <div className="tx-groups">{x.groups.map((g) => {
              const max = Math.max(1, ...g.items.map((i) => i.value));
              return (
                <div key={g.title} className="tx-g"><div className="tx-gt">{g.title}</div>
                  {g.items.map((i) => (
                    <div key={i.label} className="tx-gi"><span className="nm">{i.label}</span>
                      <span className="bar"><i style={{ width: `${(100 * i.value) / max}%` }} /></span><b>{num(i.value)}</b></div>
                  ))}
                </div>
              );
            })}</div>
          )}
          {x.rows.length > 0 && (
            <div className="tx-sec"><b>{x.rows_title} · {x.rows.length}</b>
              <div className="tbl-wrap tx-rows"><table className="tbl"><tbody>{x.rows.map((r, k) => (
                <tr key={k}><td>{r.name}</td><td className="muted">{r.info}</td><td className="muted small r">{r.extra}</td></tr>
              ))}</tbody></table></div>
            </div>
          )}
          {x.note && <p className="muted small">{x.note}</p>}
        </div>
      )}
    </Modal>
  );
}
