import { createContext, useContext } from "react";

export type Me = { username: string; full_name: string; role: string; branch_scope: number[] | null; payroll: boolean; perms: string[] };
export type Branch = { id: number; code: string; name: string; region_id: number | null; city: string | null; mode: string;
  lat?: number | null; lon?: number | null; radius_m?: number | null };
export type Dicts = {
  regions: { id: number; code: string; name: string }[];
  branches: Branch[];
  positions: { id: number; code: string; title: string }[];
  schedules: string[];
};

export const PanelCtx = createContext<{ me: Me; dicts: Dicts }>(null as any);
export const usePanel = () => useContext(PanelCtx);

export function can(me: Me, perm: string) {
  if (me.perms.includes("*") || me.perms.includes(perm)) return true;
  return perm.endsWith(".read") && me.perms.includes(perm.slice(0, -5));
}
