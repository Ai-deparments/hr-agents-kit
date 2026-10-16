"""Telegram bots. One process runs:
 - a bot per agent that has BOT_TOKEN_<AGENT>, and/or
 - one hub bot (BOT_TOKEN_HUB) that routes each message to the right agent (fewer tokens to manage).
Schedules: morning/evening attendance reports, month-end tabel, daily notifications.

python -m app.bots.main"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                           Message, ReplyKeyboardMarkup, WebAppInfo)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from ..agents.registry import AGENTS, route
from ..agents.runtime import run_agent
from ..config import cfg, settings
from ..db import SessionLocal, init_db
from ..models import BranchLead, Candidate, Employee, Vacancy
from ..rbac import Scope, scope_for_telegram
from ..services import interview, notifications, recruiting, reports

log = logging.getLogger("bots")
SYSTEM = Scope("system", "owner", None, True)


def _is_addressed(msg: Message, me_username: str) -> bool:
    if msg.chat.type == "private":
        return True
    text = msg.text or ""
    return f"@{me_username}" in text or bool(msg.reply_to_message and msg.reply_to_message.from_user
                                             and msg.reply_to_message.from_user.username == me_username)


def _answer_sync(agent: str, tg_id: int, text: str) -> str:
    with SessionLocal() as db:
        scope = scope_for_telegram(db, tg_id)
        return run_agent(db, agent, scope, text, user_key=f"tg:{tg_id}")


def miniapp_keyboard() -> ReplyKeyboardMarkup | None:
    url = settings().webapp_url
    if not url.startswith("https://"):
        return None  # Telegram requires HTTPS for Mini Apps
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🕘 Davomat", web_app=WebAppInfo(url=f"{url}/m"))]], resize_keyboard=True)


def agent_router(agent: str | None) -> Router:
    """agent=None -> hub bot with routing."""
    r = Router()

    @r.message(Command("id"))
    async def cmd_id(m: Message):
        await m.answer(f"Your Telegram ID: <code>{m.from_user.id}</code>\nGive it to HR to link your card.")

    @r.message(Command("start"))
    async def cmd_start(m: Message):
        name = AGENTS[agent].title if agent else "HR assistant"
        kb = miniapp_keyboard() if agent in (None, "hamza") else None
        if agent == "rauf":
            with SessionLocal() as db:
                if not scope_for_telegram(db, m.from_user.id).at_least("hr_head"):
                    return await start_interview(m)
        await m.answer(f"👋 {cfg('company.name')} · {name}\nWrite your question in plain words. /id — your Telegram ID.",
                       reply_markup=kb)

    @r.message(Command("guruh"))
    async def cmd_group(m: Message):
        with SessionLocal() as db:
            ok = scope_for_telegram(db, m.from_user.id).at_least("hr_head")
        await m.answer(f"Report chat id: <code>{m.chat.id}</code> — put it in REPORT_CHAT_ID." if ok else "Only HR can do this.")

    @r.message(F.text)
    async def on_text(m: Message, bot: Bot):
        me = await bot.me()
        if not _is_addressed(m, me.username):
            return
        text = m.text.replace(f"@{me.username}", "").strip()
        if agent == "rauf" and m.from_user.id in INTERVIEWS:
            return await interview_step(m)
        target = agent or route(text)
        if agent == "rauf":
            with SessionLocal() as db:
                if not scope_for_telegram(db, m.from_user.id).at_least("hr_head"):
                    return await start_interview(m)
        await bot.send_chat_action(m.chat.id, "typing")
        answer = await asyncio.to_thread(_answer_sync, target, m.from_user.id, text)
        prefix = f"<i>{AGENTS[target].title}</i>\n" if agent is None else ""
        for i in range(0, len(answer), 3900):
            await m.answer(prefix + _esc(answer[i:i + 3900]) if i == 0 else _esc(answer[i:i + 3900]))

    @r.callback_query(F.data.startswith("vac:"))
    async def pick_vacancy(c: CallbackQuery):
        INTERVIEWS[c.from_user.id] = {"vacancy_id": int(c.data[4:]), "step": "name", "answers": []}
        await c.message.answer("Your full name?")
        await c.answer()

    return r


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------- Rauf candidate interview (live dialog instead of a form) ----------------

INTERVIEWS: dict[int, dict] = {}


async def start_interview(m: Message):
    with SessionLocal() as db:
        vacs = list(db.scalars(select(Vacancy).where(Vacancy.status == "open")))
        rows = [[InlineKeyboardButton(text=f"{v.title} — {v.branch.name if v.branch else ''}", callback_data=f"vac:{v.id}")] for v in vacs]
    if not rows:
        return await m.answer("No open vacancies right now. Leave your name and phone and HR will contact you.")
    await m.answer(f"👋 {cfg('company.name')}. Which vacancy are you interested in?", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


async def interview_step(m: Message):
    st = INTERVIEWS[m.from_user.id]
    text = (m.text or "").strip()
    if text.lower() in ("/bekor", "/cancel"):
        INTERVIEWS.pop(m.from_user.id, None)
        return await m.answer("Cancelled.")
    if st["step"] == "name":
        st["name"], st["step"] = text[:160], "phone"
        return await m.answer("Your phone number?")
    if st["step"] == "phone":
        st["phone"], st["step"], st["i"] = text[:32], "q", 0
        with SessionLocal() as db:
            st["questions"] = await asyncio.to_thread(interview.questions_for, db.get(Vacancy, st["vacancy_id"]))
        return await m.answer(f"1/5. {st['questions'][0]}")
    st["answers"].append({"q": st["questions"][st["i"]], "a": text[:2000]})
    st["i"] += 1
    if st["i"] < len(st["questions"]):
        return await m.answer(f"{st['i'] + 1}/5. {st['questions'][st['i']]}")
    INTERVIEWS.pop(m.from_user.id, None)
    await m.answer("Thank you! HR will review your answers and contact you.")
    asyncio.create_task(asyncio.to_thread(_save_candidate, m.from_user.id, st))


def _save_candidate(tg_id: int, st: dict) -> None:
    with SessionLocal() as db:
        v = db.get(Vacancy, st["vacancy_id"])
        c = Candidate(vacancy_id=v.id if v else None, full_name=st["name"], phone=st["phone"], telegram_id=tg_id,
                      source="bot", answers=st["answers"])
        db.add(c)
        recruiting.apply_score(db, c, interview.score_answers(v, st["answers"]))  # no auto-reject
        db.commit()


# ---------------- scheduled reports & notifications ----------------

class Sender:
    def __init__(self, bots: dict[str, Bot]):
        self.bots = bots

    def bot(self) -> Bot | None:
        return self.bots.get("hamza") or self.bots.get("hub") or next(iter(self.bots.values()), None)

    async def to_ids(self, ids, text: str, file: tuple[str, bytes] | None = None) -> bool:
        b, ok = self.bot(), False
        for i in ids:
            try:
                await b.send_message(i, text)
                if file:
                    await b.send_document(i, BufferedInputFile(file[1], file[0]))
                ok = True
            except Exception as e:  # blocked bot, never started, etc.
                log.warning("send to %s failed: %s", i, e)
        return ok

    def management_ids(self) -> list[int]:
        s = settings()
        return sorted(s.owner_ids | s.hr_head_ids)

    async def report(self, text: str, file: tuple[str, bytes] | None = None) -> None:
        chat = settings().report_chat_id
        if chat and await self.to_ids([chat], text, file):
            return
        await self.to_ids(self.management_ids(), ("⚠️ report did not reach the group\n" if chat else "") + text, file)


async def send_reports(sender: Sender, kind: str) -> None:
    d = date.today()
    with SessionLocal() as db:
        text = reports.morning_text(db, SYSTEM, d) if kind == "morning" else reports.evening_text(db, SYSTEM, d)
        xlsx = reports.day_excel(db, SYSTEM, d)
        per_branch = []
        if cfg("reports.per_branch_to_heads", False):
            for lead in db.scalars(select(BranchLead)):
                emp = db.get(Employee, lead.employee_id)
                if emp and emp.telegram_id:
                    sc = Scope("system", "manager", {lead.branch_id})
                    t = reports.morning_text(db, sc, d) if kind == "morning" else reports.evening_text(db, sc, d)
                    per_branch.append((emp.telegram_id, t))
        tabel = None
        if kind == "evening" and (d + timedelta(days=1)).day == 1:
            tabel = (f"tabel-{d:%Y-%m}.xlsx", reports.tabel_excel(db, SYSTEM, d.strftime("%Y-%m")))
        docs = reports.documents_digest(db, SYSTEM, 30) if kind == "morning" and d.weekday() == 0 else None
    await sender.report(text, (f"davomat-{d}.xlsx", xlsx))
    for tg, t in per_branch:
        await sender.to_ids([tg], t)
    if tabel:
        await sender.report("📑 Month tabel — please check and fix in the panel if needed.", tabel)
    if docs:
        await sender.report(docs)


async def send_notifications(sender: Sender) -> None:
    with SessionLocal() as db:
        notes = notifications.collect(db)
        resolved = []
        for n in notes:
            if n.target == "hr":
                ids = sender.management_ids()
            elif n.target.startswith("branch:"):
                ids = notifications.branch_lead_telegram_ids(db, int(n.target.split(":")[1]))
            else:
                e = db.get(Employee, int(n.target.split(":")[1]))
                ids = [e.telegram_id] if e and e.telegram_id else []
            resolved.append((ids, n.text))
    for ids, text in resolved:
        await sender.to_ids(ids, text)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    init_db()
    s = settings()
    bots: dict[str, Bot] = {}
    from aiogram.client.default import DefaultBotProperties
    props = DefaultBotProperties(parse_mode="HTML")
    for name in AGENTS:
        if tok := s.bot_token(name):
            bots[name] = Bot(tok, default=props)
    if s.hub_bot_token:
        bots["hub"] = Bot(s.hub_bot_token, default=props)
    if not bots:
        raise SystemExit("No bot tokens. Set BOT_TOKEN_HUB or BOT_TOKEN_<AGENT> in .env")

    sender = Sender(bots)
    sched = AsyncIOScheduler(timezone=cfg("company.timezone", "Asia/Tashkent"))
    mh, mm = cfg("reports.morning_at", "09:00").split(":")
    eh, em = cfg("reports.evening_at", "18:30").split(":")
    sched.add_job(send_reports, "cron", hour=int(mh), minute=int(mm), args=[sender, "morning"])
    sched.add_job(send_reports, "cron", hour=int(eh), minute=int(em), args=[sender, "evening"])
    sched.add_job(send_notifications, "cron", hour=10, minute=0, args=[sender])
    sched.start()

    async def run(name: str, bot: Bot):
        dp = Dispatcher()
        dp.include_router(agent_router(None if name == "hub" else name))
        log.info("bot %s started", name)
        await dp.start_polling(bot)

    await asyncio.gather(*(run(n, b) for n, b in bots.items()))


if __name__ == "__main__":
    asyncio.run(main())
