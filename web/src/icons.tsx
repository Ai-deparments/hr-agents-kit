// Icons come from lucide-react; pages keep naming them by short keys.
import {
  BookOpen, Camera, ChartColumn, Clock, Ellipsis, FileText, Flag, Folder, Heart, House, Inbox, KeyRound, LogOut,
  MessageCircle, Moon, Network, Search, Send, ShieldCheck, Sparkles, SquareCheckBig, Sun, Table, TriangleAlert,
  Users, Wallet, type LucideIcon,
} from "lucide-react";

const I: Record<string, LucideIcon> = {
  home: House, chart: ChartColumn, inbox: Inbox, spark: Sparkles, chat: MessageCircle, team: Users, tree: Network,
  clock: Clock, grid: Table, file: FileText, check: SquareCheckBig, folder: Folder, wallet: Wallet, flag: Flag,
  send: Send, search: Search, heart: Heart, key: KeyRound, book: BookOpen, shield: ShieldCheck, sun: Sun, moon: Moon,
  warn: TriangleAlert, more: Ellipsis, camera: Camera, out: LogOut,
};

export function Ic({ n, size = 16 }: { n: string; size?: number }) {
  const C = I[n] || Ellipsis;
  return <C className="ic" size={size} strokeWidth={1.8} aria-hidden="true" />;
}
