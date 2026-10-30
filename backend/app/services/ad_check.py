"""Job-ad text checker. Every free ad text (agent variants, agent rewrites, HR's manual edit, agent tasks) passes it:
- phones, links and @handles are cut (the configured HR contacts and the vacancy's apply link are kept);
- every number must appear in the sources (vacancy card + admin-approved company facts);
- age may only be written as "18+";
- gender, appearance, nationality and religion requirements are rejected.
"2 years of experience", "опыт от 10 лет" and "attractive salary" are not age / appearance."""
from __future__ import annotations

import re

from ..config import cfg
from .recruiting import PHONE_RE

LINK_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\bt\.me/\S+|(?<![\w.])@[A-Za-z][A-Za-z0-9_]{3,}")
NUM_RE = re.compile(r"\d{1,3}(?:[   .,]\d{3})+(?!\d)|\d+(?:[.,]\d+)?")
AGE_OK = re.compile(r"(?<![\d])18\s*\+")
EXPERIENCE = re.compile(r"(?i)опыт|стаж|experience|tajrib|staj")
AGE_PATTERNS = [
    re.compile(r"(?i)\b\d{1,2}\s*(?:[-–—]|dan|до|to)?\s*\d{0,2}\s*(?:yosh\w*|years?\s+old|y\.\s?o\.)"),
    re.compile(r"(?i)(?:возраст\w*|yoshi\w*|\bage\b|\baged\b)\s*[:\-–]?\s*(?:от|до|dan|from|under|up to)?\s*\d"),
    re.compile(r"(?i)(?:\bдо|\bот|старше|младше|не старше)\s*\d{2}\s*(?:лет|года)\b"),
    re.compile(r"(?i)\byosh\s+(?:qiz|yigit|ayol|erkak)\w*"),
]
REQUIREMENT_PATTERNS = {
    "gender": [r"\bonly\s+(?:men|women|males?|females?|girls?|boys?)\b", r"\b(?:men|women|girls?|boys?)\s+only\b",
               r"\b(?:male|female)\b", r"\bgender\b",
               r"\b(?:только\s+)?(?:девушк\w*|женщин\w*|мужчин\w*|парн(?:и|ей|ям)?)\b", r"\bпол\s*[:\-–]",
               r"\b(?:qizlar\w*|ayollar\w*|erkaklar\w*|yigitlar\w*)\b", r"\bfaqat\s+(?:qiz|ayol|erkak|yigit)\w*"],
    "appearance": [r"\bappearance\b", r"\bgood[- ]looking\b", r"\bpresentable\b",
                   r"\battractive\s+(?:look\w*|girl|woman|man|person|appearance)\b",
                   r"\bslim\b", r"\b(?:height|tall)\b", r"внешност\w*", r"внешн\w+\s+вид\w*",
                   r"\bрост\s*(?:от|не ниже)?\s*\d", r"\bстройн\w*", r"\bсимпатичн\w*",
                   r"tashqi\s+ko.rinish\w*", r"\bko.rinish\w*", r"\bchiroyli\s+(?:qiz|yigit|ayol)\b", r"\bbo.yi\b"],
    "nationality": [r"\bnationality\b", r"\bethnic\w*", r"\bslavic\b", r"национальн\w*", r"славян\w*", r"\bmillat\w*",
                    r"\bfaqat\s+o.zbek\w*"],
    "religion": [r"\breligio\w*", r"\bmuslim\w*", r"\bchristian\w*", r"религи\w*", r"мусульман\w*", r"христиан\w*",
                 r"\bнамаз\w*", r"\bdin(?:i|iy|dor)?\b", r"\bmusulmon\w*", r"\bnamoz\w*"],
}
_REQ = {k: [re.compile("(?i)" + p) for p in v] for k, v in REQUIREMENT_PATTERNS.items()}


def _norm_num(tok: str) -> str:
    t = tok.replace(" ", " ").replace(" ", " ")
    if re.fullmatch(r"\d{1,3}(?:[ .,]\d{3})+", t):
        t = re.sub(r"[ .,]", "", t)
    t = t.replace(",", ".")
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t.lstrip("0") or "0"


def numbers(text: str) -> set[str]:
    return {_norm_num(m.group(0)) for m in NUM_RE.finditer(text or "")}


def contacts() -> list[str]:
    """The only contacts an ad may carry — from company.yaml, added by code."""
    c = cfg("company", {}) or {}
    return [x for x in (c.get("hr_phone"), c.get("recruiter_bot"), c.get("apply_form_url")) if x]


def check_ad(text: str, sources: list[str], keep: list[str] | None = None) -> dict:
    """Returns {ok, text, problems, removed}. 'text' has foreign phones / links cut out; `keep` (configured contacts,
    the vacancy's apply link) stays and is ignored by the number check."""
    protected = sorted({x for x in [*contacts(), *(keep or [])] if x}, key=len, reverse=True)
    removed: list[str] = []
    marks: dict[str, str] = {}
    body = text or ""
    for i, ct in enumerate(protected):
        if ct in body:
            mark = f"\x00{i}\x00"
            marks[mark] = ct
            body = body.replace(ct, mark)

    def cut(m):
        removed.append(m.group(0))
        return ""
    body = PHONE_RE.sub(cut, body)
    body = LINK_RE.sub(cut, body)
    body = re.sub(r"[ \t]{2,}", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    plain = body
    for mark in marks:
        plain = plain.replace(mark, "")
    problems: list[str] = []
    age_free = AGE_OK.sub(" ", plain)
    for p in AGE_PATTERNS:
        for m in p.finditer(age_free):
            ctx = age_free[max(0, m.start() - 30): m.end() + 30]
            if p is AGE_PATTERNS[2] and EXPERIENCE.search(ctx):
                continue  # "опыт от 10 лет" is experience, not age
            problems.append(f"age: '{m.group(0).strip()}' — only '18+' is allowed")
    for kind, pats in _REQ.items():
        for p in pats:
            m = p.search(plain)
            if m:
                problems.append(f"{kind} requirement: '{m.group(0).strip()}'")
                break
    src = set().union(*(numbers(s) for s in sources)) if sources else set()
    src.add("18")
    unknown = sorted(numbers(AGE_OK.sub(" 18 ", plain)) - src, key=lambda x: (len(x), x))
    if unknown:
        problems.append("numbers not in the vacancy or company facts: " + ", ".join(unknown[:10]))
    for mark, ct in marks.items():
        body = body.replace(mark, ct)
    return {"ok": not problems, "text": body, "problems": list(dict.fromkeys(problems)), "removed": removed}
