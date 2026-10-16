const PANEL_KEY = "hrkit.token";
const MINI_KEY = "hrkit.mini";

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key: string, v: string | null) {
  try { v === null ? localStorage.removeItem(key) : localStorage.setItem(key, v); } catch { /* storage blocked */ }
}

export const auth = {
  get panel() { return read(PANEL_KEY); },
  set panel(v: string | null) { write(PANEL_KEY, v); },
  get mini() { return read(MINI_KEY); },
  set mini(v: string | null) { write(MINI_KEY, v); },
};

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: any) { super(message); }
}

type Opts = { method?: string; body?: unknown; form?: FormData; mini?: boolean; raw?: boolean };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const token = opts.mini ? auth.mini : auth.panel;
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  const res = await fetch(path, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  if (res.status === 401 && !opts.mini && !path.endsWith("/auth/login")) {
    auth.panel = null;
    window.dispatchEvent(new Event("hrkit:logout"));
  }
  if (!res.ok) {
    let msg = res.statusText;
    let detail: any;
    try {
      const j = await res.json();
      detail = j.detail;
      msg = typeof j.detail === "string" ? j.detail : j.detail?.message || JSON.stringify(j.detail ?? j);
    } catch { /* not json */ }
    throw new ApiError(res.status, msg, detail);
  }
  if (opts.raw) return (await res.blob()) as T;
  return res.json();
}

export async function download(path: string, filename: string) {
  const blob = await api<Blob>(path, { raw: true });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const money = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : new Intl.NumberFormat("ru-RU").format(v);

export const dash = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : String(v));

export const todayISO = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
export const monthISO = () => todayISO().slice(0, 7);
export const shiftDay = (iso: string, days: number) => {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};
