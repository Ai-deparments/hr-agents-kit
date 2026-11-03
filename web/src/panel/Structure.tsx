import { useState } from "react";
import { api, dash } from "../api";
import { useT } from "../i18n";
import { Empty, Err, Modal, useLoad } from "../ui";
import { can, usePanel } from "./ctx";

type Dept = { id: number; name: string; description: string; headcount: number };

function AddForm({ fields, onSubmit, onClose, title, initial }: {
  title: string; onClose: () => void; onSubmit: (v: Record<string, string>) => Promise<unknown>;
  fields: { key: string; label: string; options?: { value: string; label: string }[]; required?: boolean }[];
  initial?: Record<string, string>;
}) {
  const t = useT();
  const [v, setV] = useState<Record<string, string>>(Object.fromEntries(fields.map((f) => [f.key, initial?.[f.key] ?? f.options?.[0]?.value ?? ""])));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={title} onClose={onClose}>
      <form className="stack" onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try { await onSubmit(v); onClose(); } catch (x: any) { setErr(x.message); } finally { setBusy(false); }
      }}>
        {fields.map((f) => (
          <label key={f.key} className="field">{f.label}
            {f.options ? (
              <select value={v[f.key]} onChange={(e) => setV({ ...v, [f.key]: e.target.value })}>
                {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ) : <input value={v[f.key]} required={f.required} onChange={(e) => setV({ ...v, [f.key]: e.target.value })} />}
          </label>
        ))}
        <Err e={err} />
        <div className="row"><span className="spacer" />
          <button type="button" className="btn" onClick={onClose}>{t("cancel")}</button>
          <button className="btn primary" disabled={busy}>{t("save")}</button>
        </div>
      </form>
    </Modal>
  );
}

function Departments() {
  const t = useT();
  const { me, reloadDicts } = usePanel();
  const admin = can(me, "*");
  const list = useLoad<Dept[]>("/api/departments");
  const [edit, setEdit] = useState<Dept | "new" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const done = () => { list.reload(); reloadDicts(); };
  return (
    <div className="card">
      <div className="card-h"><span className="card-t">{t("departments")}</span>
        <span className="card-s">{admin ? t.l("Faqat bosh admin qo'shadi", "Добавляет только главный админ", "Only the main admin adds") : t.l("Faqat ko'rish", "Только просмотр", "View only")}</span>
        <span className="card-a">{admin && <button className="btn sm primary" onClick={() => setEdit("new")}>+ {t("add")}</button>}</span></div>
      <Err e={list.error || err} />
      <div className="table-wrap"><table>
        <thead><tr><th>{t("name")}</th><th>{t("description")}</th><th className="num">{t.l("Xodimlar", "Сотр.", "Staff")}</th><th></th></tr></thead>
        <tbody>{(list.data || []).map((d) => (
          <tr key={d.id}><td>{d.name}</td><td className="muted">{dash(d.description)}</td><td className="num">{d.headcount}</td>
            <td className="num">{admin && <div className="row" style={{ justifyContent: "flex-end" }}>
              <button className="btn sm" onClick={() => setEdit(d)}>{t("edit")}</button>
              <button className="btn sm danger" disabled={d.headcount > 0} title={d.headcount > 0 ? t.l("Bo'limda xodimlar bor", "В отделе есть сотрудники", "Department has employees") : ""}
                onClick={() => api(`/api/departments/${d.id}`, { method: "DELETE" }).then(done).catch((x) => setErr(x.message))}>{t("delete")}</button>
            </div>}</td></tr>
        ))}</tbody>
      </table>{list.data?.length === 0 && <Empty />}</div>
      {edit && <AddForm title={edit === "new" ? t("departments") : edit.name} onClose={() => setEdit(null)}
        fields={[{ key: "name", label: t("name"), required: true }, { key: "description", label: t("description") }]}
        onSubmit={(v) => (edit === "new" ? api("/api/departments", { body: v }) : api(`/api/departments/${edit.id}`, { method: "PATCH", body: v })).then(done)} />}
    </div>
  );
}

type DictRow = { id: number; label: string; sub: string; initial: Record<string, string> };

function SimpleDict({ kind }: { kind: "positions" | "regions" | "branches" }) {
  const t = useT();
  const { me, dicts, reloadDicts } = usePanel();
  const [open, setOpen] = useState<DictRow | "new" | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const write = can(me, "hr.write") && (kind !== "branches" || me.branch_scope === null);
  const region = (id: number | null) => dicts.regions.find((r) => r.id === id)?.name;
  const rows: DictRow[] = kind === "positions"
    ? dicts.positions.map((p) => ({ id: p.id, label: p.title, sub: p.is_manager ? `${p.code} · ${t.l("rahbar", "руководящая", "manager")}` : p.code,
        initial: { title: p.title, is_manager: p.is_manager ? "1" : "" } }))
    : kind === "regions" ? dicts.regions.map((r) => ({ id: r.id, label: r.name, sub: r.code, initial: { name: r.name } }))
    : dicts.branches.map((b) => ({ id: b.id, label: b.name, sub: `${b.code} · ${dash(region(b.region_id))} · ${b.mode}`,
        initial: { name: b.name, city: b.city || "", region_id: b.region_id ? String(b.region_id) : "", mode: b.mode } }));
  const fields = kind === "positions" ? [{ key: "title", label: t("name"), required: true },
    { key: "is_manager", label: t.l("Rahbar lavozimi?", "Руководящая?", "Manager position?"), options: [{ value: "", label: t.l("Yo'q", "Нет", "No") }, { value: "1", label: t.l("Ha", "Да", "Yes") }] }]
    : kind === "regions" ? [{ key: "name", label: t("name"), required: true }]
    : [{ key: "name", label: t("name"), required: true }, { key: "city", label: t.l("Shahar", "Город", "City") },
       { key: "region_id", label: t("regions"), options: [{ value: "", label: "—" }, ...dicts.regions.map((r) => ({ value: String(r.id), label: r.name }))] },
       { key: "mode", label: t.l("Rejim", "Режим", "Mode"), options: [{ value: "day", label: t.l("Kunduzgi", "Дневной", "Day") }, { value: "24/7", label: "24/7" }] }];
  const submit = (v: Record<string, string>) => {
    const body: Record<string, unknown> = { ...v };
    if (kind === "positions") body.is_manager = v.is_manager === "1";
    if (kind === "branches") body.region_id = v.region_id ? Number(v.region_id) : null;
    return (open && open !== "new" ? api(`/api/${kind}/${open.id}`, { method: "PATCH", body }) : api(`/api/${kind}`, { body })).then(reloadDicts);
  };
  const remove = (r: DictRow) => {
    setErr(null);
    api(`/api/${kind}/${r.id}`, { method: "DELETE" }).then(reloadDicts).catch((x) => setErr(`${r.label}: ${x.message}`));
  };
  return (
    <div className="card">
      <div className="card-h"><span className="card-t">{t(kind)}</span><span className="card-s">{rows.length}</span>
        <span className="card-a">{write && <button className="btn sm primary" onClick={() => setOpen("new")}>+ {t("add")}</button>}</span></div>
      <Err e={err} />
      <div className="table-wrap"><table><tbody>
        {rows.map((r) => (
          <tr key={r.id}><td>{r.label}</td><td className="small muted">{r.sub}</td>
            <td className="num">{write && <div className="row" style={{ justifyContent: "flex-end" }}>
              <button className="btn sm" onClick={() => setOpen(r)}>{t("edit")}</button>
              <button className="btn sm danger" onClick={() => remove(r)}
                title={t.l("Ishlatilmayotgan bo'lsa o'chadi", "Удаляется, только если нигде не используется", "Deletes only if unused")}>{t("delete")}</button>
            </div>}</td></tr>
        ))}
      </tbody></table>{rows.length === 0 && <Empty />}</div>
      {open && <AddForm title={open === "new" ? t(kind) : open.label} fields={fields} initial={open === "new" ? undefined : open.initial}
        onClose={() => setOpen(null)} onSubmit={submit} />}
    </div>
  );
}

export default function Structure() {
  return (
    <div className="grid two">
      <Departments />
      <SimpleDict kind="positions" />
      <SimpleDict kind="regions" />
      <SimpleDict kind="branches" />
    </div>
  );
}
