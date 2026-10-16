import { createContext, useContext } from "react";

export type Lang = "en" | "uz" | "ru";

const dict: Record<string, Record<Lang, string>> = {
  dashboard: { en: "Dashboard", uz: "Boshqaruv paneli", ru: "Главная" },
  employees: { en: "Employees", uz: "Xodimlar", ru: "Сотрудники" },
  attendance: { en: "Attendance", uz: "Davomat", ru: "Посещаемость" },
  tabel: { en: "Timesheet", uz: "Tabel", ru: "Табель" },
  payroll: { en: "Payroll", uz: "Oylik", ru: "Зарплата" },
  requests: { en: "Requests", uz: "Arizalar", ru: "Заявления" },
  approvals: { en: "Approvals", uz: "Tasdiqlash", ru: "Одобрения" },
  onboarding: { en: "Onboarding", uz: "Moslashuv", ru: "Адаптация" },
  documents: { en: "Documents", uz: "Hujjatlar", ru: "Документы" },
  recruiting: { en: "Recruiting", uz: "Nomzodlar", ru: "Подбор" },
  analytics: { en: "Analytics", uz: "Tahlil", ru: "Аналитика" },
  engagement: { en: "Engagement", uz: "Jalb etilganlik", ru: "Вовлечённость" },
  agents: { en: "Agent chat", uz: "Agent bilan suhbat", ru: "Чат с агентами" },
  knowledge: { en: "Knowledge", uz: "Bilim bazasi", ru: "База знаний" },
  chats: { en: "All chats", uz: "Barcha yozishmalar", ru: "Все переписки" },
  audit: { en: "Audit log", uz: "Audit jurnali", ru: "Журнал аудита" },
  logout: { en: "Log out", uz: "Chiqish", ru: "Выйти" },
  login: { en: "Sign in", uz: "Kirish", ru: "Войти" },
  username: { en: "Username", uz: "Login", ru: "Логин" },
  password: { en: "Password", uz: "Parol", ru: "Пароль" },
  save: { en: "Save", uz: "Saqlash", ru: "Сохранить" },
  cancel: { en: "Cancel", uz: "Bekor qilish", ru: "Отмена" },
  approve: { en: "Approve", uz: "Tasdiqlash", ru: "Одобрить" },
  reject: { en: "Reject", uz: "Rad etish", ru: "Отклонить" },
  reason: { en: "Reason", uz: "Sabab", ru: "Причина" },
  add: { en: "Add", uz: "Qo'shish", ru: "Добавить" },
  search: { en: "Search", uz: "Qidirish", ru: "Поиск" },
  allBranches: { en: "All branches", uz: "Barcha filiallar", ru: "Все филиалы" },
  notMarkedNote: { en: "Not marked ≠ absent", uz: "Belgilamagan — kelmadi degani emas", ru: "Не отметился ≠ не пришёл" },
  checkIn: { en: "I'm in", uz: "Keldim", ru: "Пришёл" },
  checkOut: { en: "I'm out", uz: "Ketdim", ru: "Ушёл" },
  came: { en: "Came", uz: "Keldi", ru: "Пришёл" },
  absent: { en: "Absent", uz: "Kelmadi", ru: "Не пришёл" },
  today: { en: "Today", uz: "Bugun", ru: "Сегодня" },
  yesterday: { en: "Yesterday", uz: "Kecha", ru: "Вчера" },
  otherDay: { en: "Other day", uz: "Boshqa kun", ru: "Другой день" },
  report: { en: "Report", uz: "Raport", ru: "Рапорт" },
  month: { en: "Month", uz: "Oylik", ru: "Месяц" },
  me: { en: "Me", uz: "Men", ru: "Я" },
  advance: { en: "Advance", uz: "Avans", ru: "Аванс" },
  penalty: { en: "Penalty", uz: "Jarima", ru: "Штраф" },
  bonus: { en: "Bonus", uz: "Mukofot", ru: "Премия" },
  warning: { en: "Warning", uz: "Ogohlantirish", ru: "Предупреждение" },
  confirm: { en: "Confirm", uz: "Tasdiqlaysizmi", ru: "Подтвердить" },
  fullDay: { en: "Full day", uz: "To'liq kun", ru: "Полный день" },
  halfDay: { en: "Half day", uz: "Yarim kun", ru: "Полдня" },
  undo: { en: "Undo", uz: "Bekor qilish", ru: "Снять" },
  saving: { en: "Saving…", uz: "Saqlanmoqda…", ru: "Сохраняется…" },
  saved: { en: "Saved", uz: "Saqlandi", ru: "Сохранено" },
  send: { en: "Send", uz: "Yuborish", ru: "Отправить" },
  download: { en: "Download Excel", uz: "Excel yuklash", ru: "Скачать Excel" },
};

export const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "en", setLang: () => {} });

export function useT() {
  const { lang } = useContext(LangCtx);
  return (key: string) => dict[key]?.[lang] ?? dict[key]?.en ?? key;
}
