"""Long bare links in agent replies become a clickable word."""
from app.services.tg import short_links

HH = "https://hh.uz/resume/1dd902eb000e5d8a7500c6cd1b653334794b4e"


def test_long_bare_url_becomes_word():
    assert short_links(f"- Savdo vakili, 17 oy. {HH}") == f"- Savdo vakili, 17 oy. [Link]({HH})"
    assert short_links(f"ko'ring: {HH}.") == f"ko'ring: [Link]({HH})."


def test_short_existing_and_code_links_untouched():
    for s in ("https://hh.uz/x", f"[rezyume]({HH})", f"<{HH}>", f"`{HH}`", f"```\n{HH}\n```", ""):
        assert short_links(s) == s
