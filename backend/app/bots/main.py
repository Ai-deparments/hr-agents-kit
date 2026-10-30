"""Telegram bots. One process runs:
 - a bot per agent that has BOT_TOKEN_<AGENT>, and/or
 - one hub bot (BOT_TOKEN_HUB) that routes each message to the right agent (fewer tokens to manage).
Schedules: morning/evening attendance reports, month-end tabel, daily notifications.

python -m app.bots.main"""
from __future__ import annotations

import asyncio
import logging
import re
from contextvars import ContextVar
from datetime import date, datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                           Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo)
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


def _replied_text(m: Message) -> str:
    r = m.reply_to_message
    return (r.text or r.caption or "") if r else ""


def _last_draft(tg_id: int) -> int | None:
    with SessionLocal() as db:
        return db.scalar(select(Vacancy.id).where(Vacancy.created_by == f"tg:{tg_id}", Vacancy.status == "draft")
                         .order_by(Vacancy.id.desc()))


def _remember(tg_id: int, user_text: str, bot_text: str) -> None:
    """Bot-side vacancy steps go into the HR agent's chat history, so later free questions know about them."""
    from ..models import ChatMessage
    plain = re.sub(r"<[^>]+>", "", bot_text).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    with SessionLocal() as db:
        db.add(ChatMessage(agent="hr", user_key=f"tg:{tg_id}", role="user", text=user_text[:8000]))
        db.add(ChatMessage(agent="hr", user_key=f"tg:{tg_id}", role="assistant", text=plain[:8000]))
        db.commit()


def miniapp_keyboard(path: str = "/m", label: str = "🕘 Davomat") -> ReplyKeyboardMarkup | None:
    url = settings().webapp_url
    if not url.startswith("https://"):
        return None  # Telegram requires HTTPS for Mini Apps
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=label, web_app=WebAppInfo(url=f"{url}{path}"))]], resize_keyboard=True)


def agent_router(agent: str | None) -> Router:
    """agent=None -> hub bot with routing."""
    r = Router()

    @r.message(Command("id"))
    async def cmd_id(m: Message):
        await m.answer(f"Your Telegram ID: <code>{m.from_user.id}</code>\nGive it to HR to link your card.")

    @r.message(Command("start"))
    async def cmd_start(m: Message):
        name = AGENTS[agent].title if agent else "HR assistant"
        # attendance comes from TimePay (Face ID) — no "Davomat" check-in button; also clears it for old users
        kb = ReplyKeyboardRemove() if agent in (None, "hamza") else None
        INTERVIEWS.pop(m.from_user.id, None)
        REG.pop(m.from_user.id, None)
        arg = (m.text or "").split(maxsplit=1)[1:]  # deep link from a job post: /start vac_12
        if arg and re.fullmatch(r"vac_\d{1,9}", arg[0]):
            err = await begin_interview(m, m.from_user.id, int(arg[0][4:]))
            if err:
                await m.answer(f"ℹ️ {err}")
            return
        if arg and re.fullmatch(r"join_[A-Za-z0-9_-]{10,40}", arg[0]):
            ok = await asyncio.to_thread(_use_invite, m.from_user, arg[0][5:])
            return await m.answer(L("✅ So'rov yuborildi. Admin tasdiqlagach, login shu yerga keladi.",
                                    "✅ Запрос отправлен. После подтверждения логин придёт сюда.") if ok else
                                  L("Havola eskirgan yoki ishlatilgan.", "Ссылка устарела или уже использована."))
        if agent is None and m.chat.type == "private":
            with SessionLocal() as db:
                scope = scope_for_telegram(db, m.from_user.id)
                emp = db.get(Employee, scope.employee_id) if scope.employee_id else None
            if scope.role == "guest":
                return await stranger(m)
            if emp and scope.functions is not None:
                return await m.answer(employee_menu_text(emp.full_name, scope.functions),
                                      reply_markup=kb)
        if agent == "rauf":
            with SessionLocal() as db:
                if not scope_for_telegram(db, m.from_user.id).at_least("hr_head"):
                    return await start_interview(m)
            kb = ReplyKeyboardRemove()  # agents talk, no buttons
        await m.answer(L("Assalomu alaykum!", "Здравствуйте!"), reply_markup=kb)

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
        low = text.lower()
        uid = m.from_user.id
        if uid in INTERVIEWS:
            return await interview_step(m)
        if uid in REG:
            return await registration_step(m)
        if m.chat.type == "private":
            reply = await asyncio.to_thread(_candidate_answer, uid, text)
            if reply is not None:
                return await m.answer(_esc(reply))
        if m.chat.type == "private" and uid not in PULSE and await asyncio.to_thread(_open_exit, uid):
            PULSE[uid] = "exit"  # the ask survived a bot restart: a fired person writing back is answering it
        if m.chat.type == "private" and uid in PULSE:
            return await pulse_reply(m, low)
        if m.chat.type == "private" and SEEN_RE.search(low):
            if await asyncio.to_thread(_mark_seen, uid):
                return await m.answer(L("✅ Rahmat, belgilandi.", "✅ Спасибо, отмечено."))
        with SessionLocal() as db:
            scope = scope_for_telegram(db, uid)
        if m.chat.type == "private" and agent in (None, "rauf") and scope.at_least("hr_head"):
            card = re.search(r"📝 #(\d{1,9})", _replied_text(m))
            if card:
                VDRAFT[uid] = int(card.group(1))
            elif uid not in VDRAFT and VAC_PUBLISH.search(low):
                last = await asyncio.to_thread(_last_draft, uid)
                if last:
                    VDRAFT[uid] = last
            if uid in VDRAFT and (VAC_PUBLISH.search(low) or VAC_CANCEL.search(low) or VAC_EDIT.search(low)
                                  or VAC_VARIANTS.search(low) or await asyncio.to_thread(_has_variants_pick, VDRAFT[uid], text)):
                return await vacancy_followup(m, uid, VDRAFT[uid], low, text)
            if VACANCY_INTENT.search(low):
                return await vacancy_draft(m, text)
        # one agent per person: managers / HR / owner -> the HR agent (all tools); employees -> their own helper
        target = agent or ("hr" if scope.at_least("manager") else "suhayl")
        if m.chat.type == "private":
            if agent is None and scope.role == "guest":
                return await stranger(m)
            if not scope.has_function(target):
                return await m.answer("🔒 Эта функция вам пока не открыта — обратитесь в HR." if _ru(m) else
                                      "🔒 Bu funksiya sizga hali ochilmagan — HR'ga murojaat qiling.")
        cmd = text.split()[0].split("@")[0].lower() if text else ""
        if m.chat.type != "private" and not (target == "hamza" and cmd in GROUP_COMMANDS):
            return await m.answer("🔒 Личные данные в группе не выдаются — напишите мне в личку." if _ru(m) else
                                  "🔒 Shaxsiy ma'lumotlar guruhda berilmaydi — menga shaxsiy chatda yozing.")
        if not _llm_quota_ok(m.from_user.id):
            return await m.answer("Лимит запросов на сегодня исчерпан." if _ru(m) else "Bugungi so'rovlar limiti tugadi.")
        if agent == "rauf":
            with SessionLocal() as db:
                if not scope_for_telegram(db, m.from_user.id).at_least("hr_head"):
                    return await start_interview(m)
        await bot.send_chat_action(m.chat.id, "typing")
        quoted = _replied_text(m)
        ask = f"[Reply to this earlier message]\n{quoted[:2000]}\n[/Reply]\n\n{text}" if quoted else text
        answer = await asyncio.to_thread(_answer_sync, target, m.from_user.id, ask)
        await reply_rich(m, answer)

    return r


GROUP_COMMANDS = {"/hisobot", "/davomat"}  # aggregate-only commands allowed in group chats
_quota: dict[tuple[int, str], int] = {}


def _llm_quota_ok(tg_id: int) -> bool:
    """OWASP LLM10 (unbounded consumption): cap model calls per user per day."""
    key = (tg_id, date.today().isoformat())
    _quota[key] = _quota.get(key, 0) + 1
    if len(_quota) > 50_000:
        _quota.clear()
    return _quota[key] <= int(cfg("limits.messages_per_user_per_day", 200))


LANG: ContextVar[str] = ContextVar("lang", default="uz")


def L(uz: str, ru: str) -> str:
    """Uzbek by default (strict); Russian only for people whose Telegram is set to Russian."""
    return ru if LANG.get() == "ru" else uz


_LANG_PREF: dict[int, str] = {}
_TO_RU = re.compile(r"(ruscha|rus tilida|по-русски|на русском)")
_TO_UZ = re.compile(r"(o'?zbekcha|ozbekcha|o'zbek tilida|по-узбекски|на узбекском)")


def detect_lang(uid: int, text: str, tg_code: str | None) -> str:
    low = text.lower()
    if len(_LANG_PREF) > 50_000:  # strangers can write too: keep the map bounded
        _LANG_PREF.clear()
    if _TO_UZ.search(low):
        _LANG_PREF[uid] = "uz"
    elif _TO_RU.search(low):
        _LANG_PREF[uid] = "ru"
    elif not text.startswith("/"):
        cyr = len(re.findall(r"[а-яё]", low))
        lat = len(re.findall(r"[a-z]", low))
        if cyr + lat >= 3:
            _LANG_PREF[uid] = "ru" if cyr > lat else "uz"
    return _LANG_PREF.get(uid) or ("ru" if (tg_code or "").startswith("ru") else "uz")


def _learn_topic(chat_id: int, thread_id: int, name: str) -> None:
    from ..services import topics
    with SessionLocal() as db:
        if topics.learn(db, chat_id, thread_id, name):
            db.commit()
            log.info("forum topic %s in %s: %s", thread_id, chat_id, name)


async def topic_middleware(handler, event, data):
    msg = getattr(event, "message", None)
    if msg and msg.chat.id == settings().report_chat_id and msg.message_thread_id:
        made = msg.forum_topic_created or msg.forum_topic_edited or (
            msg.reply_to_message and (msg.reply_to_message.forum_topic_created or msg.reply_to_message.forum_topic_edited))
        if made and getattr(made, "name", None):
            await asyncio.to_thread(_learn_topic, msg.chat.id, msg.message_thread_id, made.name)
    return await handler(event, data)


async def lang_middleware(handler, event, data):
    u = data.get("event_from_user")
    msg = getattr(event, "message", None)
    LANG.set(detect_lang(u.id, (msg.text or msg.caption or "") if msg else "", u.language_code) if u else "uz")
    return await handler(event, data)


async def reply_rich(m: Message, answer: str) -> None:
    """Agent answers are Markdown: send as a Telegram rich message (real tables, headings, lists);
    plain escaped text if the client / API refuses it."""
    from aiogram.types import InputRichMessage
    if answer and len(answer) <= 32000:
        try:
            await m.bot.send_rich_message(m.chat.id, InputRichMessage(markdown=answer))
            return
        except Exception as e:
            log.warning("rich reply failed, plain text: %s", e)
    for i in range(0, len(answer or "—"), 3900):
        await m.answer(_esc((answer or "—")[i:i + 3900]))


def _ru(m) -> bool:
    """Russian only when the person's Telegram is in Russian (or they wrote Cyrillic Russian); Uzbek otherwise."""
    u = getattr(m, "from_user", None)
    return bool(u and (u.language_code or "").startswith("ru"))


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------- Rauf candidate interview (live dialog instead of a form) ----------------

INTERVIEWS: dict[int, dict] = {}


async def start_interview(m: Message):
    """Candidate: one open vacancy -> straight to consent; several -> numbered list, the person answers in words."""
    with SessionLocal() as db:
        vacs = [(v.id, v.title, v.branch.name if v.branch else "") for v in db.scalars(select(Vacancy).where(Vacancy.status == "open"))]
    if not vacs:
        return await m.answer(L("Hozir ochiq vakansiya yo'q.", "Сейчас открытых вакансий нет."))
    if len(vacs) == 1:
        err = await begin_interview(m, m.from_user.id, vacs[0][0])
        return await m.answer(err) if err else None
    INTERVIEWS[m.from_user.id] = {"step": "pick", "options": [v[0] for v in vacs], "answers": []}
    lines = "\n".join(f"{i}. {_esc(t)}" + (f" — {_esc(b)}" if b else "") for i, (_, t, b) in enumerate(vacs, 1))
    await m.answer(L("💼 Ochiq vakansiyalar:\n", "💼 Открытые вакансии:\n") + lines +
                   L("\n\nQaysi biri? Raqamini yoki nomini yozing.", "\n\nКакая? Напишите номер или название."))


def _q(text: str) -> str:
    """Question stored as 'uz\nru' -> only the user's language."""
    parts = [x for x in text.split("\n") if x.strip()]
    return (parts[1] if len(parts) > 1 and LANG.get() == "ru" else parts[0]) if parts else text


YES_RE = re.compile(r"^(ha|xa|roziman|rozi|mayli|albatta|да|согласен|согласна|ок|ok|yes|конечно)(\W|$)")
NO_RE = re.compile(r"^(yo'?q|yoq|нет|no|не хочу|kerak emas)(\W|$)")


async def interview_step(m: Message):
    st = INTERVIEWS[m.from_user.id]
    text = (m.text or "").strip()
    if text.lower() in ("/bekor", "/cancel"):
        INTERVIEWS.pop(m.from_user.id, None)
        return await m.answer(L("Bekor qilindi.", "Отменено. /start"))
    low = text.lower()
    if st["step"] == "pick":
        vid = None
        if low.isdigit() and 1 <= int(low) <= len(st["options"]):
            vid = st["options"][int(low) - 1]
        else:
            with SessionLocal() as db:
                hit = [v.id for v in db.scalars(select(Vacancy).where(Vacancy.id.in_(st["options"]))) if low and low in v.title.lower()]
            vid = hit[0] if len(hit) == 1 else None
        if not vid:
            return await m.answer(L("Raqamini yozing (masalan: 1).", "Напишите номер (например: 1)."))
        INTERVIEWS.pop(m.from_user.id, None)
        err = await begin_interview(m, m.from_user.id, vid)
        return await m.answer(err) if err else None
    if st["step"] == "consent":
        if YES_RE.search(low):
            st["step"], st["consent_at"] = "name", datetime.now().isoformat(timespec="seconds")
            return await m.answer(L("Ism-familiyangiz?", "Ваши имя и фамилия?"))
        if NO_RE.search(low):
            INTERVIEWS.pop(m.from_user.id, None)
            return await m.answer(L("Tushunarli, ma'lumot saqlanmadi.", "Понятно, данные не сохранены."))
        return await m.answer(L("«Ha» yoki «yo'q» deb yozing.", "Напишите «да» или «нет»."))
    if st["step"] == "name":
        st["name"], st["step"] = text[:160], "phone"
        return await m.answer(L("Telefon raqamingiz?", "Ваш номер телефона?"))
    if st["step"] == "phone":
        st["phone"], st["step"], st["i"] = text[:32], "q", 0
        with SessionLocal() as db:
            st["questions"] = await asyncio.to_thread(interview.questions_for, db.get(Vacancy, st["vacancy_id"]))
        return await m.answer(f"1/5. {_esc(_q(st['questions'][0]))}")
    st["answers"].append({"q": st["questions"][st["i"]], "a": text[:2000]})
    st["i"] += 1
    if st["i"] < len(st["questions"]):
        return await m.answer(f"{st['i'] + 1}/5. {_esc(_q(st['questions'][st['i']]))}")
    INTERVIEWS.pop(m.from_user.id, None)
    await m.answer("✅ Rahmat! Javoblaringiz HR bo'limiga yuborildi, siz bilan bog'lanishadi.\n"
                   "✅ Спасибо! Ваши ответы отправлены в HR, с вами свяжутся.")
    asyncio.create_task(_save_and_notify(m.bot, m.from_user.id, st))


async def _save_and_notify(bot: Bot, tg_id: int, st: dict) -> None:
    title, score = await asyncio.to_thread(_save_candidate, tg_id, st)
    s = settings()
    for i in sorted(s.owner_ids | s.hr_head_ids):
        try:
            await bot.send_message(i, f"🆕 Yangi nomzod: <b>{_esc(st['name'])}</b>\n"
                                      f"{_esc(title or '—')} · ball: {score if score is not None else '—'}")
        except Exception as e:
            log.warning("candidate notice to %s failed: %s", i, e)


def _save_candidate(tg_id: int, st: dict) -> tuple[str | None, int | None]:
    with SessionLocal() as db:
        v = db.get(Vacancy, st["vacancy_id"])
        c = Candidate(vacancy_id=v.id if v else None, full_name=st["name"], phone=st["phone"], telegram_id=tg_id,
                      source="bot", answers=st["answers"],
                      consent_at=datetime.fromisoformat(st["consent_at"]) if st.get("consent_at") else None)
        db.add(c)
        recruiting.apply_score(db, c, interview.score_answers(v, st["answers"]))  # no auto-reject
        db.commit()
        return (v.title if v else None), c.score


async def begin_interview(m: Message, tg_id: int, vid: int) -> str | None:
    """Consent step for a vacancy (from the list or a /start vac_N deep link). Returns an error text or None."""
    with SessionLocal() as db:
        v = db.get(Vacancy, vid)
        today = sum(1 for x in db.scalars(select(Candidate).where(Candidate.telegram_id == tg_id))
                    if x.created_at.date() == date.today())
        title = v.title if v else ""
    if v and v.status == "draft":
        return L("Bu vakansiya hali e'lon qilinmagan (qoralama)", "Вакансия ещё не опубликована (черновик)")
    if not v or v.status != "open":
        return L("Bu vakansiya yopilgan", "Вакансия закрыта")
    if today >= int(cfg("limits.interviews_per_candidate_per_day", 3)):
        return L("Bugungi limit tugadi — ertaga urinib ko'ring", "Лимит на сегодня исчерпан")
    INTERVIEWS[tg_id] = {"vacancy_id": vid, "step": "consent", "answers": []}
    days = cfg("recruiting.retention_days", 180)
    await m.answer(f"💼 <b>{_esc(title)}</b>\n\n" + L(
        f"ℹ️ {_esc(cfg('company.name'))} suhbat javoblaringizni vakansiya bo'yicha qaror uchun saqlaydi ({days} kungacha). "
        "Javoblarni AI baholaydi, qarorni HR qabul qiladi.\n\nRozimisiz? «Ha» yoki «yo'q» deb yozing.",
        f"ℹ️ {_esc(cfg('company.name'))} сохраняет ваши ответы для решения по вакансии (до {days} дней). "
        "Ответы оценивает ИИ, решает HR.\n\nСогласны? Напишите «да» или «нет»."))
    return None


# ---------------- HR: vacancies written by the recruiter agent, edited and published from Telegram ----------------

VDRAFT: dict[int, int] = {}  # HR tg id -> vacancy draft being discussed (plain-text follow-ups edit it)
_VAC_NOUN = re.compile(r"(vakans|ваканси|e'lon|elon|объявлени|job post)")
_VAC_VERB = re.compile(r"(yoz|tuz|yarat|tay+orla|tay+or|post|напиш|состав|созда|сделай|подготов|write|create)")
VAC_PUBLISH = re.compile(r"(e'?lon qil|chop et|joyla|tasdiqla|publish|опубликуй|выложи|размести|утверждаю)")
VAC_CANCEL = re.compile(r"^(bekor|o'chir|отмен|удали|не надо)")
VAC_EDIT = re.compile(r"(maosh|oylik|talab|vazifa|ish vaqt|grafik|filial|matn|qisqa|uzun|qo'sh|olib tashla|o'zgartir|"
                      r"qayta yoz|зарплат|оклад|требован|обязанност|график|филиал|текст|короче|длинн|добав|убери|измени|перепиш)")
VAC_VARIANTS = re.compile(r"(variant|вариант)")


class _Intent:
    """'vakansiya yoz', 'составь вакансию' — a noun AND a create verb, so 'ochiq vakansiyalar qancha?' stays a question."""
    @staticmethod
    def search(t: str) -> bool:
        return bool(_VAC_NOUN.search(t) and _VAC_VERB.search(t) and "?" not in t)


VACANCY_INTENT = _Intent()


def vacancy_link(vid: int) -> str:
    url = settings().webapp_url.rstrip("/")
    return f"{url}/jobs#{vid}" if url.startswith("https://") else ""


def _vacancy_card(vid: int, show_variants: bool = False) -> str:
    from ..services import vacancies
    with SessionLocal() as db:
        v = db.get(Vacancy, vid)
        miss = vacancies.missing(v)
        ad = v.ad_text or ""
        vs = [(a.n, a.text) for a in vacancies.variants(db, v)] if show_variants else []
    names = {"branch": L("filial", "филиал"), "salary_text": L("maosh", "зарплата"),
             "schedule_text": L("ish vaqti", "график"), "title": L("lavozim", "должность")}
    need = (L("\n\n⚠️ Yozing: ", "\n\n⚠️ Укажите: ") + ", ".join(names.get(x, x) for x in miss)) if miss else ""
    if vs:
        body = "\n".join(f"<b>{n}-variant</b>\n<blockquote expandable>{_esc(t)[:1500]}</blockquote>" for n, t in vs)
        hint = L("\n\nQaysi biri? «1» yoki «2» deb yozing, yoki nimani o'zgartirishni yozing.",
                 "\n\nКакой? Напишите «1» или «2», или что изменить.")
        return f"📝 <b>#{vid}</b>\n{body}{need}{hint}"
    hint = L("\n\n«e'lon qil» — chop etaman · «variantlar» — 2 ta variant · o'zgartirish — nimani yozing · «bekor» — o'chiraman",
             "\n\n«опубликуй» — выложу · «варианты» — 2 варианта · правка — напишите что изменить · «отмена» — удалю")
    return f"📝 <b>#{vid}</b>\n<blockquote>{_esc(ad)[:3200]}</blockquote>{need}{hint}"


def _has_variants_pick(vid: int, text: str) -> bool:
    """A short reply like '2' / 'ikkinchisi' right after the variants were shown."""
    from ..services import vacancies
    if vacancies.pick_variant(text) is None:
        return False
    with SessionLocal() as db:
        v = db.get(Vacancy, vid)
        return bool(v and vacancies.variants(db, v))


def _vacancy_variants(tg_id: int, vid: int) -> str | None:
    from ..services import vacancies
    with SessionLocal() as db:
        v = db.get(Vacancy, vid)
        if not v:
            return L("Topilmadi", "Не найдено")
        try:
            vacancies.make_variants(db, _hr_scope(tg_id), v)
        except ValueError as e:
            return str(e)
        db.commit()
    return None


def _vacancy_reply(tg_id: int, vid: int, text: str) -> tuple[str, str | None]:
    """HR's words after the variants / on a chosen text: pick (code or the model's 1/2 label) or a checked rewrite.
    Returns (kind, error): kind = picked | rewritten | fields."""
    from ..services import vacancies
    with SessionLocal() as db:
        v = db.get(Vacancy, vid)
        if not v:
            return "fields", L("Topilmadi", "Не найдено")
        scope = _hr_scope(tg_id)
        has_variants = bool(vacancies.variants(db, v))
        n = vacancies.pick_variant(text) if has_variants else None
        if has_variants and n is None and not VAC_EDIT.search(text.lower()):
            n = vacancies.pick_variant_ai(text)
        try:
            if n:
                vacancies.choose(db, scope, v, n)
                db.commit()
                return "picked", None
            if v.ad_custom:  # a chosen / edited text: the agent rewrites the text itself, the checker decides
                res = vacancies.rewrite_text(db, v, text)
                if res.get("error"):
                    return "rewritten", res["error"]
                if not res["ok"]:
                    return "rewritten", "; ".join(res["problems"])
                vacancies.set_ad(db, scope, v, res["text"], f"AI: {text[:200]}")
                db.commit()
                return "rewritten", None
        except ValueError as e:
            return "picked", str(e)
    return "fields", _vacancy_rewrite(tg_id, vid, text)


def _hr_scope(tg_id: int) -> Scope:
    with SessionLocal() as db:
        s = scope_for_telegram(db, tg_id)
    return Scope(f"tg:{tg_id}", s.role, s.branch_ids, s.payroll, s.employee_id)


def _vacancy_new(tg_id: int, brief: str) -> int:
    from ..services import vacancies
    with SessionLocal() as db:
        v = vacancies.from_brief(db, _hr_scope(tg_id), brief)
        db.commit()
        return v.id


def _vacancy_rewrite(tg_id: int, vid: int, comment: str) -> str | None:
    from ..services import vacancies
    with SessionLocal() as db:
        v = db.get(Vacancy, vid)
        if not v:
            return L("Topilmadi", "Не найдено")
        try:
            vacancies.rewrite(db, _hr_scope(tg_id), v, comment)
        except ValueError as e:
            return str(e)
        db.commit()
    return None


def _vacancy_finish(tg_id: int, vid: int, act: str) -> tuple[bool, str]:
    """act = publish | cancel. Returns (ok, platforms)."""
    from ..services import vacancies
    with SessionLocal() as db:
        v = db.get(Vacancy, vid)
        if not v:
            return False, ""
        scope = _hr_scope(tg_id)
        if act == "cancel":
            vacancies.close(db, scope, v)
            db.commit()
            return True, ""
        try:  # human approval: bot list + public page (+ channel when configured)
            done = vacancies.publish(db, scope, v, web=True, channel=bool(cfg("recruiting.jobs_channel")))
        except ValueError as e:
            log.warning("publish #%s: %s", vid, e)
            db.rollback()
            return False, ""
        db.commit()
        return True, ", ".join(sorted(done))


async def vacancy_draft(m: Message, brief: str) -> None:
    await m.bot.send_chat_action(m.chat.id, "typing")
    vid = await asyncio.to_thread(_vacancy_new, m.from_user.id, brief)
    VDRAFT[m.from_user.id] = vid
    card = await asyncio.to_thread(_vacancy_card, vid)
    await asyncio.to_thread(_remember, m.from_user.id, brief, card)
    await m.answer(card)


async def vacancy_followup(m: Message, uid: int, vid: int, low: str, text: str) -> None:
    """HR answers the draft in words: publish (only the exact confirm word) / cancel / variants / pick / any change."""
    from ..services import vacancies
    if VAC_PUBLISH.search(low) and not VAC_CANCEL.search(low) and not vacancies.is_confirm(text):
        return await m.answer(L(f"Chop etish uchun aynan «{vacancies.confirm_words()[0]}» deb yozing.",
                                f"Чтобы опубликовать, напишите ровно «{vacancies.confirm_words()[0]}»."))
    if VAC_PUBLISH.search(low) or VAC_CANCEL.search(low):
        act = "publish" if VAC_PUBLISH.search(low) else "cancel"
        ok, done = await asyncio.to_thread(_vacancy_finish, uid, vid, act)
        if act == "cancel":
            VDRAFT.pop(uid, None)
            return await m.answer(L(f"✖️ #{vid} o'chirildi.", f"✖️ #{vid} удалена."))
        if not ok:
            return await m.answer(L("⚠️ Chop etilmadi: filial, maosh va ish vaqtini yozing.",
                                    "⚠️ Не опубликовано: укажите филиал, зарплату и график."))
        VDRAFT.pop(uid, None)
        out = (L(f"✅ #{vid} chop etildi: {_esc(done)}", f"✅ #{vid} опубликована: {_esc(done)}")
               + (f"\n{_esc(vacancy_link(vid))}" if vacancy_link(vid) else ""))
        await asyncio.to_thread(_remember, uid, text, out)
        return await m.answer(out)
    await m.bot.send_chat_action(m.chat.id, "typing")
    if VAC_VARIANTS.search(low) and vacancies.pick_variant(text) is None:  # "2 ta variant yoz", "варианты"
        err = await asyncio.to_thread(_vacancy_variants, uid, vid)
        if err:
            return await m.answer(f"⚠️ {_esc(err)}")
        card = await asyncio.to_thread(_vacancy_card, vid, True)
        await asyncio.to_thread(_remember, uid, text, card)
        return await m.answer(card)
    _kind, err = await asyncio.to_thread(_vacancy_reply, uid, vid, text)
    if err:
        return await m.answer(f"⚠️ {_esc(err)}")
    card = await asyncio.to_thread(_vacancy_card, vid)
    await asyncio.to_thread(_remember, uid, text, card)
    await m.answer(card)


# ---------------- onboarding "ko'rdim" and pulse answers in words ----------------

SEEN_RE = re.compile(r"^(ko'?rdim|korib chiqdim|ko'rib chiqdim|tanishdim|посмотрел|посмотрела|просмотрел|ознакомил)")
PULSE: dict[int, str] = {}  # tg id -> "enps" | "exit" waiting for an answer in words


def _mark_seen(tg_id: int) -> bool:
    from ..models import MaterialSend
    with SessionLocal() as db:
        e = db.scalar(select(Employee).where(Employee.telegram_id == tg_id))
        if not e:
            return False
        s = db.scalar(select(MaterialSend).where(MaterialSend.employee_id == e.id, MaterialSend.queued.is_(True),
                                                 MaterialSend.viewed_at.is_(None)).order_by(MaterialSend.sent_at.desc()))
        if not s:
            return False
        s.viewed_at = datetime.now()
        db.commit()
        return True


EXIT_WORDS = {"pay": ("maosh", "oylik", "pul", "зарплат", "деньг"), "schedule": ("grafik", "vaqt", "график", "смен"),
              "manager": ("rahbar", "boshliq", "руковод", "начальн"), "workload": ("yuklama", "charch", "нагруз", "много работ"),
              "growth": ("o'sish", "rivoj", "рост", "развит"), "personal": ("shaxsiy", "oila", "личн", "семь")}


def _open_exit(tg_id: int) -> bool:
    from ..models import PulseSent
    with SessionLocal() as db:
        e = db.scalar(select(Employee).where(Employee.telegram_id == tg_id, Employee.status == "fired"))
        return bool(e) and db.scalar(select(PulseSent.id).where(
            PulseSent.employee_id == e.id, PulseSent.kind == "exit", PulseSent.answered.is_(False),
            PulseSent.month == date.today().strftime("%Y-%m"))) is not None


async def pulse_reply(m: Message, low: str) -> None:
    from ..services import engagement
    kind = PULSE[m.from_user.id]
    if kind == "enps":
        mm = re.search(r"\b(10|[0-9])\b", low)
        if not mm:
            return await m.answer(L("0 dan 10 gacha raqam yozing.", "Напишите число от 0 до 10."))
        score, reason = int(mm.group(1)), None
    else:
        reason = next((k for k, words in EXIT_WORDS.items() if any(w in low for w in words)), "other")
        score = 0
    with SessionLocal() as db:
        e = db.scalar(select(Employee).where(Employee.telegram_id == m.from_user.id))
        ok = bool(e) and engagement.record_pulse(db, e, kind, score, reason=reason,
                                                 comment=m.text if kind == "exit" else None)
        db.commit()
    PULSE.pop(m.from_user.id, None)
    await m.answer(L("Rahmat! Javob anonim saqlandi.", "Спасибо! Ответ сохранён анонимно.") if ok else
                   L("Allaqachon javob bergansiz.", "Вы уже ответили."))


# ---------------- /start for guests: sticker + one question, answered in words ----------------

WELCOME: dict[int, list[int]] = {}  # tg id -> message ids cleared after the person answers
REG: dict[int, dict] = {}            # "I am an employee" dialog state
CAND_RE = re.compile(r"(ish(ga)? (kir|qidir|izla)|ishga|vakans|ish kerak|работ|ваканси|устро|ищу)")
EMP_RE = re.compile(r"(xodim|ishlayman|ishlaym|shu yerda|сотрудник|работаю|я здесь)")


async def welcome(m: Message) -> None:
    ids = [m.message_id]
    if sticker := cfg("bot.welcome_sticker"):
        try:
            ids.append((await m.answer_sticker(sticker)).message_id)
        except Exception as e:
            log.warning("welcome sticker failed: %s", e)
    co = _esc(cfg('company.name', ''))
    msg = await m.answer(L(f"👋 Assalomu alaykum! Men {co} HR agentiman.\nShu yerda ishlaysizmi yoki ishga kirmoqchimisiz?",
                           f"👋 Здравствуйте! Я HR-агент {co}.\nВы здесь работаете или хотите устроиться?"))
    WELCOME[m.from_user.id] = ids + [msg.message_id]


async def guest_reply(m: Message, low: str) -> None:
    """Guest answered in words: employee -> registration, candidate -> interview, unclear -> ask again shortly."""
    emp, cand = bool(EMP_RE.search(low)), bool(CAND_RE.search(low))
    if emp == cand:
        return await welcome(m) if m.from_user.id not in WELCOME else await m.answer(
            L("Ishlaysizmi yoki ishga kirmoqchimisiz?", "Вы работаете здесь или хотите устроиться?"))
    await clear_welcome(m.bot, m.chat.id, m.from_user.id)
    if cand:
        return await start_interview(m)
    await start_registration(m, m.from_user)


# ---------------- strangers: no answer, an access request for HR (panel -> Ruxsat so'rovlari) ----------------

def _record_access(user, bot_name: str) -> bool:
    """Upsert the person's request; returns True when it is new (HR gets one notice, not one per message)."""
    from ..models import Registration
    with SessionLocal() as db:
        r = db.scalar(select(Registration).where(Registration.telegram_id == user.id, Registration.source == "access")
                      .order_by(Registration.id.desc()))
        name = " ".join(x for x in (user.first_name, user.last_name) if x)[:160] or f"tg {user.id}"
        if r and r.status in ("pending", "rejected"):
            r.requests = (r.requests or 1) + 1
            r.last_at = datetime.now()
            r.tg_username, r.full_name = user.username, name
            r.bots = sorted(set((r.bots or []) + [bot_name]))
            db.commit()
            return False
        db.add(Registration(telegram_id=user.id, tg_username=user.username, full_name=name, position_text="",
                            region_text="", source="access", bots=[bot_name], last_at=datetime.now(), requests=1))
        db.commit()
        return True


async def stranger(m: Message) -> None:
    """Unknown person: the agent stays silent (it is not a public bot); HR decides in the panel."""
    me = await m.bot.me()
    if await asyncio.to_thread(_record_access, m.from_user, me.username or "bot"):
        s = settings()
        uname = f" @{_esc(m.from_user.username)}" if m.from_user.username else ""
        for i in sorted(s.owner_ids | s.hr_head_ids):
            try:
                await m.bot.send_message(i, f"🔐 Ruxsat so'rovi: <b>{_esc(m.from_user.full_name)}</b>{uname} · "
                                            f"<code>{m.from_user.id}</code>\nPanel → Ruxsat so'rovlari")
            except Exception as e:
                log.warning("access notice to %s failed: %s", i, e)


def _use_invite(user, token: str) -> bool:
    from ..models import PanelInvite
    with SessionLocal() as db:
        i = db.scalar(select(PanelInvite).where(PanelInvite.token == token))
        if not i or i.status != "open" or i.expires_at < datetime.now():
            return False
        i.status, i.telegram_id, i.used_at = "pending", user.id, datetime.now()
        i.tg_name = " ".join(x for x in (user.first_name, user.last_name) if x)[:160]
        i.tg_username = user.username
        db.commit()
        return True


async def clear_welcome(bot: Bot, chat_id: int, tg_id: int, extra: int | None = None) -> None:
    """Wipe the greeting (and the user's /start) so the chosen flow starts on a clean screen."""
    ids = set(WELCOME.pop(tg_id, [])) | ({extra} if extra else set())
    for mid in sorted(ids):
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass  # older than 48 h or already gone


def employee_menu_text(name: str, functions: set[str]) -> str:
    first = _esc((name or "").split()[0]) if name else ""
    return L(f"Assalomu alaykum, {first}!", f"Здравствуйте, {first}!")


async def start_registration(m: Message, user) -> None:
    from ..models import Registration
    with SessionLocal() as db:
        pending = db.scalar(select(Registration.id).where(Registration.telegram_id == user.id, Registration.status == "pending"))
    if pending:
        return await m.answer(L("⏳ Arizangiz HR'da ko'rib chiqilmoqda.", "Ваша заявка уже на рассмотрении в HR."))
    REG[user.id] = {"step": "name"}
    await m.answer(L("👔 <b>Ro'yxatdan o'tish</b>\n\n1/3. Ism va familiyangiz?", "👔 <b>Регистрация</b>\n\n1/3. Ваши имя и фамилия?"))


async def registration_step(m: Message, value: str | None = None, user=None) -> None:
    from ..models import Position, Region, Registration
    user = user or m.from_user
    st = REG.get(user.id)
    if not st:
        return
    text = (value if value is not None else (m.text or "")).strip()
    if text.lower() in ("/bekor", "/cancel"):
        REG.pop(user.id, None)
        return await m.answer(L("Bekor qilindi.", "Отменено. /start"))
    with SessionLocal() as db:
        if st["step"] == "name":
            if len(text) < 3 or len(text.split()) < 2:
                return await m.answer(L("Ism va familiyani to'liq yozing.", "Напишите имя и фамилию полностью."))
            st["name"], st["step"] = text[:160], "position"
            items = [(p.id, p.title) for p in db.scalars(select(Position).order_by(Position.title))]
            return await m.answer(L("2/3. Lavozimingiz? Tanlang yoki yozing.", "2/3. Ваша должность? Выберите или напишите."))
        if st["step"] == "position":
            p = db.get(Position, int(text)) if value is not None and text.isdigit() else None
            st["position"], st["step"] = (p.title if p else text)[:160], "region"
            items = [(r.id, r.name) for r in db.scalars(select(Region).order_by(Region.name))]
            return await m.answer(L("3/3. Qaysi hududda ishlaysiz?", "3/3. В каком регионе вы работаете?"))
        r = db.get(Region, int(text)) if value is not None and text.isdigit() else None
        reg = Registration(telegram_id=user.id, tg_username=user.username, full_name=st["name"],
                           position_text=st["position"], region_text=(r.name if r else text)[:160])
        db.add(reg)
        db.commit()
    REG.pop(user.id, None)
    await m.answer("✅ Ariza HR bo'limiga yuborildi. Tasdiqlangach, sizga xabar keladi.\n"
                   "✅ Заявка отправлена в HR. После подтверждения придёт уведомление.")
    s = settings()
    for i in sorted(s.owner_ids | s.hr_head_ids):
        try:
            await m.bot.send_message(i, f"🆕 Xodim arizasi: <b>{_esc(st['name'])}</b>\n"
                                        f"{_esc(st['position'])} · {_esc(reg.region_text)}")
        except Exception as e:
            log.warning("registration notice to %s failed: %s", i, e)


async def send_outbox(sender: Sender) -> None:
    """Deliver messages queued by the panel (registration decisions, broadcasts, onboarding, candidates).
    Each row is claimed (committed) before sending, so a crash or a second worker never sends it twice."""
    from ..services import outbox
    b = sender.bot()
    with SessionLocal() as db:
        for o in outbox.claim(db, 25):
            ok, err = False, None
            try:
                if o.file_path:
                    from aiogram.types import FSInputFile
                    f, cap = FSInputFile(o.file_path), _esc(o.text)[:1000]
                    if o.file_path.lower().endswith((".mp4", ".mov", ".m4v", ".webm")):
                        await b.send_video(o.telegram_id, f, caption=cap, supports_streaming=True)
                    else:
                        await b.send_document(o.telegram_id, f, caption=cap)
                else:
                    from ..services import topics
                    thread = topics.thread_for(db, o.topic) if o.topic else None
                    await b.send_message(o.telegram_id, _esc(o.text), message_thread_id=thread)
                ok = True
            except Exception as e:
                err = str(e)
            outbox.finish(db, o, ok, err)
            await asyncio.sleep(0.05)  # stay under Telegram's 30 msg/s


# ---------------- scheduled reports & notifications ----------------

class Sender:
    def __init__(self, bots: dict[str, Bot]):
        self.bots = bots

    def bot(self) -> Bot | None:
        return self.bots.get("hamza") or self.bots.get("hub") or next(iter(self.bots.values()), None)

    async def to_ids(self, ids, text: str, file: tuple[str, bytes] | None = None, rich: str | None = None,
                     thread: int | None = None) -> bool:
        """rich = rich Markdown (sendRichMessage: real tables/headings); `text` (HTML) is the fallback.
        thread = forum topic id in a group chat."""
        from aiogram.types import InputRichMessage, LinkPreviewOptions
        from ..services import tg
        b, ok = self.bot(), False
        for i in ids:
            try:
                sent = False
                if rich and len(rich) <= 32000:
                    try:
                        await b.send_rich_message(i, InputRichMessage(markdown=rich), message_thread_id=thread)
                        sent = True
                    except Exception as e:  # older clients / API reject -> plain HTML below
                        log.warning("rich message to %s failed, falling back to HTML: %s", i, e)
                if not sent:
                    for part in tg.split(text):  # ≤4096, cut only between blocks so no tag is broken
                        await b.send_message(i, part, link_preview_options=LinkPreviewOptions(is_disabled=True),
                                             message_thread_id=thread)
                if file:
                    await b.send_document(i, BufferedInputFile(file[1], file[0]), message_thread_id=thread)
                ok = True
            except Exception as e:  # blocked bot, never started, etc.
                log.warning("send to %s failed: %s", i, e)
        return ok

    def management_ids(self) -> list[int]:
        s = settings()
        return sorted(s.owner_ids | s.hr_head_ids)

    async def report(self, text: str, file: tuple[str, bytes] | None = None, rich: str | None = None,
                     kind: str = "digest") -> None:
        """Into the reports group, in the forum topic that fits `kind` (see services/topics.py)."""
        from ..services import topics
        chat = settings().report_chat_id
        if chat:
            with SessionLocal() as db:
                thread = topics.thread_for(db, kind)
            if await self.to_ids([chat], text, file, rich, thread=thread):
                return
        await self.to_ids(self.management_ids(), ("⚠️ report did not reach the group\n" if chat else "") + text, file,
                          (("> ⚠️ report did not reach the group\n\n" if chat else "") + rich) if rich else None)


async def send_reports(sender: Sender, kind: str) -> None:
    d = date.today()
    with SessionLocal() as db:
        text = reports.morning_text(db, SYSTEM, d) if kind == "morning" else reports.evening_text(db, SYSTEM, d)
        rich = reports.morning_md(db, SYSTEM, d) if kind == "morning" else reports.evening_md(db, SYSTEM, d)
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
        # names the camera could not match: once a day (full day seen), private chats only — never the group
        unknown = reports.camera_unmatched_text(db, d) if kind == "evening" else None
    await sender.report(text, (f"davomat-{d}.xlsx", xlsx), rich, kind="attendance")
    if unknown:
        await sender.to_ids(sender.management_ids(), unknown)
    for tg, t in per_branch:
        await sender.to_ids([tg], t)
    if tabel:
        await sender.report("📑 <b>Oylik tabel</b> — tekshiring, kerak bo'lsa panelda tuzating.", tabel, kind="attendance")
    if docs:
        await sender.report(docs, kind="documents")


async def send_notifications(sender: Sender) -> None:
    with SessionLocal() as db:
        notes = notifications.collect(db)
        resolved = []
        for n in notes:
            if n.target == "hr":
                ids = sender.management_ids()
            elif n.target == "tabel_closers":  # HR heads close the tabel; owners when no HR head is set
                ids = sorted(settings().hr_head_ids) or sorted(settings().owner_ids)
            elif n.target.startswith("branch:"):
                ids = notifications.branch_lead_telegram_ids(db, int(n.target.split(":")[1]))
            else:
                e = db.get(Employee, int(n.target.split(":")[1]))
                ids = [e.telegram_id] if e and e.telegram_id else []
            resolved.append((ids, n.text, n.kind))
        db.commit()  # PulseSent marks
    b = sender.bot()
    for ids, text, kind in resolved:
        if kind in ("pulse_enps", "pulse_exit"):
            for i in ids:
                try:
                    k = kind.split("_")[1]
                    ask = ("\n\n0 dan 10 gacha raqam bilan javob bering." if k == "enps" else
                           "\n\nSababini bir-ikki so'z bilan yozing (maosh, grafik, rahbar, yuklama, o'sish, shaxsiy).")
                    await b.send_message(i, _esc(text) + ask)
                    PULSE[i] = k
                except Exception as e:
                    log.warning("pulse to %s failed: %s", i, e)
        else:
            await sender.to_ids(ids, _esc(text))  # notices are plain text; names must not become HTML


async def send_weekly(sender: Sender, monday: date | None = None) -> None:
    """Monday 09:00: last week's CEO digest into the reports topic (rich + Excel)."""
    from ..services import weekly
    monday = monday or date.today() - timedelta(days=date.today().weekday() + 7)
    with SessionLocal() as db:
        w = weekly.week_data(db, SYSTEM, monday)
    await sender.report(weekly.week_text(w), (f"hafta-{monday:%Y-%m-%d}.xlsx", weekly.week_excel(w)), weekly.week_md(w), kind="digest")


def _md_plain(md: str) -> str:
    """Rich Markdown -> plain HTML-escaped fallback text (premium emoji become their fallback character)."""
    return _esc(re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", md).replace("**", "").replace("#", "").replace("\\", ""))


async def send_topic_report(sender: Sender, kind: str, evening: bool = False) -> None:
    from ..services import topic_reports as tr
    with SessionLocal() as db:
        if kind == "analytics":
            md = tr.analytics_evening_md(db, SYSTEM) if evening else tr.analytics_md(db, SYSTEM)
        else:
            fn = {"recruiting": tr.recruiting_md, "onboarding": tr.onboarding_md, "payroll": tr.payroll_md}[kind]
            md = fn(db, SYSTEM, evening=evening)
    if md:
        await sender.report(_md_plain(md), None, md, kind=kind)


async def send_weekly_signals(sender: Sender) -> None:
    """Weekly per-branch signals: one count line to the group; branch lines only privately
    (HR leaders: all branches, branch heads: their own)."""
    from ..services import topic_reports as tr
    with SessionLocal() as db:
        group = tr.weekly_signals_md(db, SYSTEM)
        full = tr.weekly_signals_md(db, SYSTEM, private=True)
        heads = []
        for lead in db.scalars(select(BranchLead)):
            emp = db.get(Employee, lead.employee_id)
            if emp and emp.telegram_id:
                if md := tr.weekly_signals_md(db, Scope("system", "manager", {lead.branch_id}), private=True):
                    heads.append((emp.telegram_id, md))

    if group and settings().report_chat_id:
        await sender.report(_md_plain(group), None, group, kind="analytics")
    if full:
        await sender.to_ids(sender.management_ids(), _md_plain(full), rich=full)
    for tg, md in heads:
        await sender.to_ids([tg], _md_plain(md), rich=md)


async def draft_nudges(sender: Sender) -> None:
    """Monday: discipline reminder drafts; HR approves them in the panel (nothing reaches employees before that)."""
    from ..services import nudges
    with SessionLocal() as db:
        made = nudges.draft_week(db, SYSTEM)
        db.commit()
    if made:
        url = settings().webapp_url.rstrip("/")
        await sender.report(f"📝 <b>{len(made)}</b> ta intizom eslatmasi tayyor — panelda ko'rib chiqing va yuboring: "
                            f"{url}/attendance", kind="attendance")


async def send_talk_reminders(sender: Sender) -> None:
    """Morning reminder about today's onboarding talks: to each employee and one summary to HR."""
    from ..models import MaterialSend, OnboardingMaterial
    start = datetime.combine(date.today(), datetime.min.time())
    with SessionLocal() as db:
        rows = [(s, db.get(OnboardingMaterial, s.material_id)) for s in db.scalars(
            select(MaterialSend).where(MaterialSend.talk_done.is_(False), MaterialSend.talk_at >= start,
                                       MaterialSend.talk_at < start + timedelta(days=1)))]
        items = [(s.employee.telegram_id, s.employee.full_name, m.title if m else "—", s.talk_at, s.talk_with) for s, m in rows]
    if not items:
        return
    for tg, _name, title, at, who in items:
        if tg:
            await sender.to_ids([tg], f"🗓 Bugun suhbat: <b>{_esc(title)}</b>\n{at:%H:%M} · {_esc(who or '')}")
    lines = "\n".join(f"• {at:%H:%M} {_esc(name)} — {_esc(title)} ({_esc(who or '')})" for _tg, name, title, at, who in items)
    await sender.to_ids(sender.management_ids(), f"🗓 Bugungi onboarding suhbatlari:\n{lines}")


def _candidate_answer(tg_id: int, text: str) -> str | None:
    """Hiring conversation (slot choice, a booked interview to move / cancel, an offer) -> reply; None when there is none."""
    from ..services import hiring
    with SessionLocal() as db:
        res = hiring.handle(db, tg_id, text)
        if res is None:
            return None
        reply, notes = res
        from ..models import Outbox
        group = settings().report_chat_id
        if group:  # hiring events go to the recruiter topic of the HR group, once
            for note in dict.fromkeys(n for _, n in notes):
                db.add(Outbox(telegram_id=group, text=note, topic="recruiting"))
        else:
            for hr, note in notes:
                db.add(Outbox(telegram_id=hr, text=note))
        db.commit()
        return reply


def interview_reminders() -> None:
    """Day before at 18:00 and 1 h before (each at most once: slot flags + outbox dedupe)."""
    from ..services import hiring, outbox
    with SessionLocal() as db:
        for tg, text in hiring.remind(db):
            outbox.queue(db, tg, text, dedupe=outbox.key("remind", tg, text))
        db.commit()


def deliver_onboarding() -> None:
    """Course items due today -> outbox (sent by send_outbox within seconds)."""
    from ..services import onboarding_media
    with SessionLocal() as db:
        n = onboarding_media.deliver_due(db)
        db.commit()
    log.info("onboarding course: %s item(s) queued", n)


def run_agent_jobs() -> None:
    """Panel 'task for the agent' (vacancy ad text): run queued jobs; a person applies the checked result."""
    from ..services import vacancies
    with SessionLocal() as db:
        n = vacancies.run_jobs(db)
    if n:
        log.info("agent jobs: %s done", n)


def purge_personal_data() -> None:
    with SessionLocal() as db:
        n = recruiting.purge_candidates(db)
        db.commit()
    log.info("retention purge: %s candidate(s) anonymised", n)


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
    mh, mm = cfg("reports.morning_at", "10:00").split(":")
    eh, em = cfg("reports.evening_at", "21:00").split(":")
    sched.add_job(send_reports, "cron", hour=int(mh), minute=int(mm), args=[sender, "morning"])
    sched.add_job(send_reports, "cron", hour=int(eh), minute=int(em), args=[sender, "evening"])
    sched.add_job(send_weekly, "cron", day_of_week="mon", hour=int(mh), minute=int(mm) + 1, args=[sender])
    sched.add_job(draft_nudges, "cron", day_of_week="mon", hour=int(mh), minute=int(mm) + 5, args=[sender])
    if ws := cfg("reports.weekly_signals"):
        wh, wm = str(ws.get("at", "09:15")).split(":")
        sched.add_job(send_weekly_signals, "cron", day_of_week=int(ws.get("weekday", 0)), hour=int(wh), minute=int(wm), args=[sender])
    # every topic gets a morning and an evening report at the same times as attendance (skipped when nothing to say)
    for kind in ("recruiting", "onboarding", "payroll", "analytics"):
        sched.add_job(send_topic_report, "cron", hour=int(mh), minute=int(mm), args=[sender, kind, False])
        sched.add_job(send_topic_report, "cron", hour=int(eh), minute=int(em), args=[sender, kind, True])
    sched.add_job(send_notifications, "cron", hour=10, minute=0, args=[sender])
    sched.add_job(purge_personal_data, "cron", hour=3, minute=0)
    sched.add_job(send_outbox, "interval", seconds=10, args=[sender], max_instances=1)
    sched.add_job(send_talk_reminders, "cron", hour=8, minute=30, args=[sender])
    sched.add_job(deliver_onboarding, "cron", hour=9, minute=30)
    sched.add_job(interview_reminders, "interval", minutes=5, max_instances=1)
    sched.add_job(run_agent_jobs, "interval", minutes=1, max_instances=1)
    sched.start()

    async def run(name: str, bot: Bot):
        dp = Dispatcher()
        dp.update.outer_middleware(lang_middleware)
        dp.update.outer_middleware(topic_middleware)
        dp.include_router(agent_router(None if name == "hub" else name))
        log.info("bot %s started", name)
        await dp.start_polling(bot)

    await asyncio.gather(*(run(n, b) for n, b in bots.items()))


if __name__ == "__main__":
    asyncio.run(main())
