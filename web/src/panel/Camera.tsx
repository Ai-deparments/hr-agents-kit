import { useState } from "react";
import { shiftDay, todayISO } from "../api";
import { useT } from "../i18n";
import { Empty, Err, Tile, useLoad } from "../ui";

/** Read-only: what the AI camera reported. A mark becomes attendance only for one exact name match. */
export default function Camera() {
  const t = useT();
  const [day, setDay] = useState(todayISO());
  const { data: s, error } = useLoad<any>(`/api/camera?day=${day}`, [day]);
  const days = useLoad<any[]>("/api/camera/days?days=14");
  const maxVisits = Math.max(1, ...(s?.hourly_visits || []).map((h: any) => h.count));
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="row">
        <button className="btn sm" onClick={() => setDay(shiftDay(day, -1))}>←</button>
        <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        <button className="btn sm" onClick={() => setDay(shiftDay(day, 1))}>→</button>
      </div>
      <Err e={error || days.error} />
      {s && !s.configured && <div className="note">{t.l(
        "Kamera o'chiq: .env'da CAMERA_WEBHOOK_SECRET ni o'rnating va kamera xizmatiga /api/webhooks/camera manzilini bering.",
        "Камера выключена: задайте CAMERA_WEBHOOK_SECRET в .env и дайте сервису камеры адрес /api/webhooks/camera.",
        "The camera webhook is off: set CAMERA_WEBHOOK_SECRET in .env and give the camera service /api/webhooks/camera.")}</div>}
      {s && <>
        <div className="grid tiles">
          <Tile label={t.l("Keldi (kamera)", "Пришли (камера)", "Arrived (camera)")} value={s.arrived} sub={s.date} />
          <Tile label={t.l("Kechikdi (kamera)", "Опоздали (камера)", "Late (camera)")} value={s.late} sub={t.l("shaxsiy jadvalga ko'ra", "по личному графику", "vs. personal schedule")} />
          <Tile label={t.l("Tanilmadi", "Не распознаны", "Not recognised")} value={s.unmatched_count ?? "—"}
            sub={s.unmatched_count === null ? t.l("faqat butun tarmoq uchun", "только для всей сети", "network-wide users only") : t.l("saqlandi, taxmin qilinmadi", "сохранены, не угадываются", "stored, not guessed")} />
          <Tile label={t.l("Tashrif buyuruvchilar", "Посетители", "Visitors")} value={s.visits_total} sub={t.l("soatlik sonlar yig'indisi", "сумма по часам", "sum of hourly counts")} />
        </div>
        <div className="note">{t.l("Inson belgisi (Keldim, rahbar, HR tuzatishi) har doim kamera belgisidan ustun. Rasmlar saqlanmaydi.",
          "Отметки людей (check-in, руководитель, правка HR) всегда главнее камеры. Фото не сохраняются.",
          "Human marks (check-in, team lead, HR edit) always win over camera marks. Photos are never stored.")}</div>
        <div className="grid two">
          <div className="card">
            <h2>{t.l("Hodisalar", "События", "Events")}</h2>
            <div className="table-wrap"><table>
              <thead><tr><th>{t.l("Vaqt", "Время", "Time")}</th><th>{t("c_name")}</th><th>{t("c_branch")}</th><th>{t.l("Hodisa", "Событие", "Event")}</th><th>{t.l("Davomat", "Посещаемость", "Attendance")}</th></tr></thead>
              <tbody>{s.events.map((e: any) => (
                <tr key={e.id}><td className="mono">{e.time}</td><td>{e.full_name}</td><td className="small">{e.branch}</td>
                  <td>{e.kind === "arrived" ? t.l("keldi", "пришёл", "arrived") : t.l("ketdi", "ушёл", "left")}</td>
                  <td className="small">{e.applied ? t.l("yozildi", "записано", "applied") : e.note || t.l("oldingi belgi qoldi", "оставлена прежняя отметка", "kept the earlier/later mark")}</td></tr>
              ))}</tbody>
            </table></div>
            {s.events.length === 0 && <Empty />}
          </div>
          <div className="card">
            <h2>{t.l("Soatlar bo'yicha tashriflar", "Посетители по часам", "Visitors by hour")}</h2>
            {s.hourly_visits.length === 0 && <Empty />}
            <div className="stack" style={{ gap: 6 }}>
              {s.hourly_visits.map((h: any) => (
                <div key={h.hour} className="row" style={{ flexWrap: "nowrap" }}>
                  <span className="mono small" style={{ width: 48 }}>{String(h.hour).padStart(2, "0")}:00</span>
                  <div className="bar" style={{ flex: 1, marginTop: 0 }}><span style={{ width: `${(100 * h.count) / maxVisits}%` }} /></div>
                  <span className="num small" style={{ width: 40, textAlign: "right" }}>{h.count}</span>
                </div>
              ))}
            </div>
            {s.unmatched && <>
              <h2 style={{ marginTop: 14 }}>{t.l("Tanilmaganlar", "Не распознаны", "Not recognised")}</h2>
              {s.unmatched.length === 0 ? <Empty /> :
                <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{s.unmatched.map((n: string) => <li key={n}>{n}</li>)}</ul>}
              <div className="muted small" style={{ marginTop: 6 }}>{t.l("Ismni xodim kartasida yoki kamera xizmatida tuzating.",
                "Исправьте имя в карточке сотрудника или в сервисе камеры.", "Fix the name in the employee card or in the camera service.")}</div>
            </>}
          </div>
        </div>
      </>}
      {days.data && <div className="card">
        <h2>{t.l("Oxirgi 14 kun", "Последние 14 дней", "Last 14 days")}</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>{t.l("Kun", "День", "Day")}</th><th className="num">{t.l("Keldi", "Пришли", "Arrived")}</th><th className="num">{t("c_late")}</th>
            <th className="num">{t.l("Tanilmadi", "Не распознаны", "Not recognised")}</th><th className="num">{t.l("Tashrif", "Посетители", "Visitors")}</th></tr></thead>
          <tbody>{days.data.map((d) => (
            <tr key={d.date} className="click" onClick={() => setDay(d.date)}><td className="mono">{d.date}</td><td className="num">{d.arrived}</td>
              <td className="num">{d.late}</td><td className="num">{d.unmatched_count ?? "—"}</td><td className="num">{d.visits_total}</td></tr>
          ))}</tbody>
        </table></div>
      </div>}
    </div>
  );
}
