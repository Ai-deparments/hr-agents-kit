"""hh.uz (HeadHunter) résumé search for the recruiter. READ-ONLY.
Uses an employer OAuth token that another service already keeps (HH_TOKEN_FILE):
we only read it and never refresh or write it, so the two services can't fight over a rotating refresh token.
Contacts are never bought here (that costs money) — a person opens them on hh.uz.
HH_DEMO=1 returns sample résumés so the screen can be shown before hh is connected."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

API = "https://api.hh.ru"
AREAS = {"uz": 97, "tashkent": 2759, "samarkand": 2760, "bukhara": 2761, "andijan": 2762, "fergana": 2764, "namangan": 2765}
EXPERIENCE = {"noExperience", "between1And3", "between3And6", "moreThan6"}
# "N+" years = every hh bucket from N up (hh takes the experience param several times)
EXPERIENCE_MIN = {"1+": ["between1And3", "between3And6", "moreThan6"], "3+": ["between3And6", "moreThan6"],
                  "6+": ["moreThan6"]}


def experience_values(experience: str) -> list[str]:
    """'1+' / 'between1And3' / 'between1And3,between3And6' -> hh experience values."""
    e = (experience or "").strip()
    if e in EXPERIENCE_MIN:
        return EXPERIENCE_MIN[e]
    vals = [x.strip() for x in e.split(",") if x.strip()]
    if any(v not in EXPERIENCE for v in vals):
        raise HhError("Bad experience")
    return vals


class HhError(Exception):
    pass


def _token_file() -> Path | None:
    p = os.getenv("HH_TOKEN_FILE", "")
    return Path(p) if p else None


def demo() -> bool:
    """Sample résumés only until the real token appears: once the employer connects hh.uz, live mode switches on by itself."""
    f = _token_file()
    return os.getenv("HH_DEMO", "0") == "1" and not (f and f.is_file())


def status() -> dict:
    f = _token_file()
    if demo():
        return {"mode": "demo", "ok": True, "detail": "Demo: namunaviy rezyumelar · Демо: пример резюме"}
    if not f:
        return {"mode": "off", "ok": False, "detail": "HH_TOKEN_FILE sozlanmagan · не настроен"}
    if not f.is_file():
        return {"mode": "off", "ok": False, "detail": "hh.uz hali ulanmagan: ish beruvchi bir marta ruxsat berishi kerak · "
                                                     "hh.uz ещё не подключён: работодатель должен один раз дать доступ"}
    try:
        tok = json.loads(f.read_text())
    except (OSError, ValueError):
        return {"mode": "off", "ok": False, "detail": "token fayli o'qilmadi · файл токена не читается"}
    expired = time.time() >= tok.get("expires_at", 0)
    return {"mode": "live", "ok": not expired,
            "detail": "token muddati tugagan — asosiy servis yangilaydi · токен истёк, его обновит основной сервис" if expired else "ulangan · подключено"}


def _ua() -> str:
    # hh blacklists placeholder contacts like example.com (400 bad_user_agent)
    return os.getenv("HH_USER_AGENT", "HRAgentsKit/1.0 (github.com/Ai-deparments/hr-agents-kit)")


def search(text: str, area: str = "uz", experience: str = "", salary_to: int | None = None, page: int = 0) -> dict:
    if not text.strip() or len(text) > 200:
        raise HhError("Qidiruv so'zi 1–200 belgi · Запрос 1–200 символов")
    exp = experience_values(experience)
    if area not in AREAS:
        raise HhError(f"area: {', '.join(AREAS)}")
    if demo():
        return _demo(text, area)
    st = status()
    if not st["ok"]:
        raise HhError(st["detail"])
    tok = json.loads(_token_file().read_text())["access_token"]
    params = [("text", text), ("area", AREAS[area]), ("per_page", 20), ("page", max(0, min(page, 19))),
              ("order_by", "relevance"), ("host", "hh.uz")] + [("experience", x) for x in exp]
    if salary_to:
        params += [("salary_to", salary_to), ("currency", "UZS")]
    try:
        r = httpx.get(f"{API}/resumes", params=params, timeout=30,
                      headers={"Authorization": f"Bearer {tok}", "HH-User-Agent": _ua(), "User-Agent": _ua()})
    except httpx.HTTPError as e:
        raise HhError(f"hh ulanish xatosi · ошибка связи: {e}") from e
    if r.status_code == 403:
        raise HhError("hh: rezyume bazasiga pullik dostup yo'q · нет платного доступа к базе резюме")
    if r.status_code >= 400:
        raise HhError(f"hh xatosi · ошибка hh ({r.status_code})")
    j = r.json()
    return {"found": int(j.get("found") or 0), "items": [_item(x) for x in j.get("items") or []], "mode": "live"}


def _item(r: dict) -> dict:
    sal = r.get("salary") or {}
    exp = (r.get("experience") or [{}])[0] if r.get("experience") else {}
    months = (r.get("total_experience") or {}).get("months")
    return {"id": r.get("id"), "title": r.get("title"), "age": r.get("age"), "area": (r.get("area") or {}).get("name"),
            "salary": sal.get("amount"), "currency": sal.get("currency"),
            "experience_months": months, "last_company": exp.get("company"), "last_position": exp.get("position"),
            "updated": (r.get("updated_at") or "")[:10], "url": r.get("alternate_url"),
            "name": " ".join(x for x in (r.get("last_name"), r.get("first_name")) if x) or None}


_DEMO = [
    ("Farmatsevt / Фармацевт", 27, "Toshkent", 7_000_000, 48, "Dori-Darmon", "Farmatsevt"),
    ("Провизор", 31, "Toshkent", 9_000_000, 96, "Grand Pharm", "Zav. apteka"),
    ("Kassir-sotuvchi", 22, "Samarqand", 4_500_000, 18, "Korzinka", "Kassir"),
    ("Супервайзер торговых агентов", 34, "Toshkent", 12_000_000, 120, "Coca-Cola Uzbekistan", "Supervisor"),
    ("HR-менеджер / рекрутер", 29, "Toshkent", 8_000_000, 60, "Uzum", "Recruiter"),
    ("Kuryer (o'z mashinasi bilan)", 25, "Toshkent", 5_000_000, 30, "Yandex Eats", "Kuryer"),
    ("Бухгалтер", 38, "Buxoro", 8_500_000, 150, "Artel", "Buxgalter"),
    ("Sotuv menejeri", 26, "Toshkent", 6_500_000, 36, "Texnomart", "Sotuv bo'yicha menejer"),
]


def _demo(text: str, area: str) -> dict:
    words = [w for w in text.lower().replace("/", " ").split() if len(w) > 2]
    items = []
    for i, (title, age, city, sal, months, comp, pos) in enumerate(_DEMO):
        hay = f"{title} {pos} {comp}".lower()
        if words and not any(w[:5] in hay for w in words):
            continue
        items.append({"id": f"demo{i + 1}", "title": title, "age": age, "area": city, "salary": sal, "currency": "UZS",
                      "experience_months": months, "last_company": comp, "last_position": pos, "updated": "2026-10-20",
                      "url": None, "name": None})
    if not items:  # demo always shows something
        items = [_demo("x", area)["items"][0]] if words else []
    return {"found": len(items), "items": items, "mode": "demo"}
