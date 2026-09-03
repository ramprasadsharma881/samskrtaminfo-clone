#!/usr/bin/env python3
"""Build the modernised samskrtam.info into dist/.

Everything the reader sees is rendered ahead of time: the pages work with
JavaScript switched off, they carry their own text for search engines, and
they can be served by any static host (or opened straight off disk).
JavaScript only adds the conveniences - toggling registers of a verse,
filtering, theming, remembering the reader's preferences.
"""
from __future__ import annotations

import html
import json
import math
import re
import shutil
import unicodedata
from urllib.parse import quote
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"
ASSETS = ROOT / "src" / "assets"      # authored: stylesheet + scripts
MEDIA = ROOT / "original-site"        # the school's own images, audio, fonts, PDFs
DIST = ROOT / "dist"

# Media is not copied into src/ — the mirror is its single source, and the build
# assembles dist/assets/ from both. Keeps one copy of 21 MB of media in the repo.
MEDIA_MAP = [
    ("images", "assets/img"),
    ("audio", "assets/audio"),
    ("assets/pdfs", "assets/pdfs"),
]
MEDIA_FILES = [
    ("img/favicon.png", "assets/img/favicon.png"),
    ("fonts/Sanskrit2003.ttf", "assets/fonts/Sanskrit2003.ttf"),
    ("fonts/suranna.ttf", "assets/fonts/suranna.ttf"),
    ("fonts/CharterIndologique.otf", "assets/fonts/CharterIndologique.otf"),
]


def media_exists(rel: str) -> bool:
    """Is this asset path (as the original references it) actually present?"""
    return (MEDIA / rel).exists()

SITE_NAME = "Samskrtam"
SITE_ORG = "स्वर्वाणीप्रकाश-सेवानिकुञ्जम्"
SITE_ORG_LATIN = "Svarvāṇī Prakāśa · Sevā Nikuñjam"
MOTTO = "संस्कृतं स्वधर्मस्य मूलम्"
BASE_URL = "https://samskrtam.info"
EMAIL = "samskrta.usha@gmail.com"
YEAR = date.today().year

pages_written: list[tuple[str, float]] = []


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def load(name: str):
    return json.loads((DATA / f"{name}.json").read_text("utf-8"))


def e(text) -> str:
    return html.escape(str(text or ""), quote=True)


def slug(text: str, fallback: str = "item") -> str:
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or fallback


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()


def asset(path: str) -> str:
    """URL-safe asset path (some original filenames contain spaces)."""
    return quote(str(path), safe="/-_.~")


def rel(depth: int) -> str:
    return "../" * depth if depth else ""


DEVA_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")


def deva_num(text: str) -> str:
    """Verse numbers are set in Devanagari numerals, as a scribe would."""
    return str(text).translate(DEVA_DIGITS)


def unique_ids(prefix: str):
    """Anchor-id allocator.

    The school's numbering repeats in a few places (two verses numbered ०२४,
    a duplicated ११५१). The displayed folio number stays exactly as written;
    only the anchor gets a disambiguating suffix, so every verse remains
    reachable by link.
    """
    seen: dict[str, int] = {}

    def make(raw: str) -> str:
        base = f"{prefix}-{slug(raw, raw)}"
        n = seen.get(base, 0)
        seen[base] = n + 1
        return base if n == 0 else f"{base}-{chr(ord('a') + n)}"

    return make


def folio(text: str) -> str:
    """An illuminated medallion: ॥ ०३ ॥ — danda, numeral, danda."""
    return (f'<span class="verse__num"><span class="danda">॥</span>'
            f'<span class="folio">{e(deva_num(text))}</span>'
            f'<span class="danda">॥</span></span>')


PADA_END = re.compile(r"(?<=।)\s*")
VERSE_NUM = re.compile(r"(॥[^॥]*॥)\s*$")


def set_padas(value: str) -> str:
    """Set a verse as hemistiches: one pāda group per line, a breath at the
    caesura where the single danda falls, the verse number hanging after.

    Only plain readings are re-set; anything already carrying markup is left
    exactly as the school wrote it."""
    if "<" in value or "।" not in value:
        return value
    text = value.strip()
    number = ""
    m = VERSE_NUM.search(text)
    if m:
        number = m.group(1)
        text = text[: m.start()].strip()
    parts = [p.strip() for p in PADA_END.split(text) if p.strip()]
    if len(parts) < 2 and not number:
        return value
    out = []
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        cls = "pada pada--break" if part.rstrip().endswith("।") and not last else "pada"
        tail = f' <span class="pada--num">{number}</span>' if last and number else ""
        out.append(f'<span class="{cls}">{part}{tail}</span>')
    if number and not parts:
        out.append(f'<span class="pada"><span class="pada--num">{number}</span></span>')
    return "".join(out)


GLOSS_EQ = re.compile(r"\s*=\s*")


def set_glosses(value: str) -> str:
    """प्रतिपदार्थः is a run of `term = gloss;` pairs. Set each on its own line
    with the headword picked out, so the eye can scan the terms."""
    if "<" in value or "=" not in value:
        return value
    out = []
    for chunk in value.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" in chunk:
            term, _, rest = chunk.partition("=")
            out.append(
                f'<span class="gloss"><span class="gloss__term">{term.strip()}</span>'
                f'<span class="gloss__eq">=</span>'
                f'<span class="gloss__def">{rest.strip()}</span></span>'
            )
        else:
            out.append(f'<span class="gloss">{chunk}</span>')
    return "".join(out) if out else value


# "Translation-" on the Narasimha page, "Meaning-" on the Totakāṣṭaka page;
# sometimes its own block, sometimes just another line inside the verse block.
GLOSS_CUE = re.compile(r"^\s*(?:Translation|Meaning)\s*[-–:]\s*", re.I)
LABEL_CUE = re.compile(r"^\s*(?:Mulam[^:]*|Introduction)\s*:\s*", re.I)
# Devanagari letters only — U+0964/5 are the daṇḍa, which IAST lines also use,
# so including them would make every transliterated line look like Devanagari.
DEVA_LETTER = re.compile(r"[\u0900-\u0963\u0966-\u097f]")
RULE_OFF = set("-–—_ ")


def _lines(block: str) -> list[str]:
    return [ln.strip() for ln in block.split("<br>") if ln.strip()]


def stanzas(body: str) -> list[dict]:
    """Recover a stotra's stanza structure from its <br>-separated blob.

    Each block is one verse. Within a block the Devanagari setting, its IAST
    transliteration and an English rendering may all be present, in that order,
    the last introduced by "Translation-" or "Meaning-".
    """
    body = LABEL_CUE.sub("", body.strip(), count=1)
    out: list[dict] = []
    for block in re.split(r"(?:<br>\s*){2,}", body):
        lines = _lines(block)
        if not lines:
            continue

        # a translation block that stands on its own belongs to the verse above
        if GLOSS_CUE.match(lines[0]) and len(out):
            gloss = GLOSS_CUE.sub("", "<br>".join(lines), count=1)
            out[-1]["gloss"] = gloss
            continue

        gloss = ""
        for i, ln in enumerate(lines):
            if GLOSS_CUE.match(ln):
                gloss = GLOSS_CUE.sub("", "<br>".join(lines[i:]), count=1)
                lines = lines[:i]
                break
        if not lines:
            if gloss and out:
                out[-1]["gloss"] = gloss
            continue

        if all(set(ln) <= RULE_OFF for ln in lines):
            continue                                   # the ------- rule-offs

        deva = [ln for ln in lines if DEVA_LETTER.search(ln)]
        latn = [ln for ln in lines if not DEVA_LETTER.search(ln)]
        entry: dict = {"kind": "verse" if deva else "iast", "lines": deva or latn}
        if deva and latn:
            entry["iast"] = latn
        if gloss:
            entry["gloss"] = gloss
        out.append(entry)
    return out


def render_stanzas(body: str) -> str:
    """A stotra set as verses: Devanagari crowned, IAST beneath it, the English
    rendering below both — instead of one continuous run of <br>s."""
    items = stanzas(body)
    if not items:
        return body
    parts = []
    for i, st in enumerate(items):
        # the opening ॥श्री…॥ / अथ … lines name the stotra; they are not verses
        if i < 2 and len(st["lines"]) == 1 and not st.get("gloss") and not st.get("iast"):
            parts.append(f'<p class="stanza__head deva">{st["lines"][0]}</p>')
            continue
        lines = "".join(f'<span class="stanza__line">{ln}</span>' for ln in st["lines"])
        iast = ""
        if st.get("iast"):
            iast = ('<div class="stanza__iast latn">'
                    + "".join(f'<span class="stanza__line">{ln}</span>' for ln in st["iast"])
                    + "</div>")
        gloss = f'<div class="stanza__gloss latn">{st["gloss"]}</div>' if st.get("gloss") else ""
        script = "deva" if st["kind"] == "verse" else "latn"
        parts.append(
            f'<div class="stanza"><div class="stanza__text {script}">{lines}</div>{iast}{gloss}</div>'
        )
    return "".join(parts)


URL_RE = re.compile(r"(?<![\w/@.\-])(https?://[^\s<>\u0900-\u097f\u0c00-\u0c7f\]\)]+)")


def linkify(text: str) -> str:
    """Make the school's source citations clickable again.

    Several of them sit inside <pre> blocks and verse cells, where the original
    markup carried an <a> that text extraction necessarily flattened. The URL
    itself survived; this puts the anchor back."""
    if "<a " in text:
        return text
    return URL_RE.sub(lambda m: f'<a href="{m.group(1)}" rel="noopener">{m.group(1)}</a>', text)


def set_register(key: str, value: str) -> str:
    if key == "moolam":
        return set_padas(value)
    if key == "prati":
        return set_glosses(value)
    return linkify(value)


def search_key(*parts) -> str:
    """Build the haystack used by the client-side filters.

    Only for items whose visible text is not itself searchable (a card whose
    keywords never appear on screen).  Anything whose own text is enough is
    marked with a bare ``data-search`` and the client reads its textContent -
    that keeps large corpora from carrying a second copy of themselves in an
    attribute.
    """
    flat: list[str] = []
    for p in parts:
        if isinstance(p, (list, tuple)):
            flat.extend(str(x) for x in p)
        elif p:
            flat.append(str(p))
    return e(re.sub(r"\s+", " ", " ".join(flat))[:600])


def write(path: str, markup: str) -> None:
    out = DIST / path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markup, "utf-8")
    pages_written.append((path, out.stat().st_size / 1024))


# --------------------------------------------------------------------------- #
# icons
# --------------------------------------------------------------------------- #
ICON = {
    "menu": '<path d="M3 6h18M3 12h18M3 18h18"/>',
    "close": '<path d="M18 6 6 18M6 6l12 12"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/>',
    "text": '<path d="M4 7V5h16v2M9 19h6M12 5v14"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "up": '<path d="m6 15 6-6 6 6"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1"/>',
    "play": '<path d="m6 4 14 8-14 8z" fill="currentColor" stroke="none"/>',
    "pdf": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
}

SOCIAL_ICON = {
    "facebook": '<path d="M22 12a10 10 0 1 0-11.6 9.9v-7H7.9V12h2.5V9.8c0-2.5 1.5-3.9 3.8-3.9 1.1 0 2.2.2 2.2.2v2.4h-1.2c-1.2 0-1.6.8-1.6 1.6V12h2.7l-.4 2.9h-2.3v7A10 10 0 0 0 22 12z"/>',
    "youtube": '<path d="M23 12s0-3.2-.4-4.7a2.5 2.5 0 0 0-1.8-1.8C19.3 5 12 5 12 5s-7.3 0-8.8.5a2.5 2.5 0 0 0-1.8 1.8C1 8.8 1 12 1 12s0 3.2.4 4.7a2.5 2.5 0 0 0 1.8 1.8C4.7 19 12 19 12 19s7.3 0 8.8-.5a2.5 2.5 0 0 0 1.8-1.8C23 15.2 23 12 23 12zM9.8 15.1V8.9l6 3.1z"/>',
    "instagram": '<path d="M12 2.2c3.2 0 3.6 0 4.9.1 1.2.1 1.8.2 2.2.4.6.2 1 .5 1.4.9.4.4.7.8.9 1.4.2.4.4 1 .4 2.2.1 1.3.1 1.7.1 4.9s0 3.6-.1 4.9c-.1 1.2-.2 1.8-.4 2.2-.2.6-.5 1-.9 1.4-.4.4-.8.7-1.4.9-.4.2-1 .4-2.2.4-1.3.1-1.7.1-4.9.1s-3.6 0-4.9-.1c-1.2-.1-1.8-.2-2.2-.4a3.8 3.8 0 0 1-1.4-.9 3.8 3.8 0 0 1-.9-1.4c-.2-.4-.4-1-.4-2.2C2.2 15.6 2.2 15.2 2.2 12s0-3.6.1-4.9c.1-1.2.2-1.8.4-2.2.2-.6.5-1 .9-1.4.4-.4.8-.7 1.4-.9.4-.2 1-.4 2.2-.4 1.3-.1 1.7-.1 4.8-.1zm0 3.2a6.6 6.6 0 1 0 0 13.2 6.6 6.6 0 0 0 0-13.2zm0 10.9a4.3 4.3 0 1 1 0-8.6 4.3 4.3 0 0 1 0 8.6zm8.4-11.2a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/>',
    "twitter": '<path d="M18.2 2H21l-6.4 7.3L22 22h-5.9l-4.6-6-5.3 6H3.4l6.8-7.8L2.3 2h6l4.2 5.5zm-1 18h1.6L7.9 3.7H6.2z"/>',
    "pinterest": '<path d="M12 2a10 10 0 0 0-3.6 19.3c-.1-.8-.2-2 0-2.9l1.2-5s-.3-.6-.3-1.5c0-1.4.8-2.5 1.8-2.5.9 0 1.3.6 1.3 1.4 0 .9-.6 2.2-.9 3.4-.2 1 .5 1.8 1.5 1.8 1.8 0 3.1-1.9 3.1-4.6 0-2.4-1.7-4.1-4.2-4.1-2.9 0-4.6 2.1-4.6 4.4 0 .9.3 1.8.8 2.3.1.1.1.2.1.3l-.3 1.1c0 .2-.1.2-.3.1-1.3-.6-2-2.4-2-3.9 0-3.2 2.3-6.1 6.7-6.1 3.5 0 6.2 2.5 6.2 5.8 0 3.5-2.2 6.3-5.2 6.3-1 0-2-.5-2.3-1.2l-.6 2.4c-.2.9-.8 2-1.2 2.6A10 10 0 1 0 12 2z"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1" fill="none" stroke="currentColor" stroke-width="2"/>',
}


def icon(name: str, cls: str = "") -> str:
    body = ICON.get(name, "")
    c = f' class="{cls}"' if cls else ""
    return f'<svg{c} viewBox="0 0 24 24" aria-hidden="true">{body}</svg>'


# --------------------------------------------------------------------------- #
# chrome
# --------------------------------------------------------------------------- #
NAV = [
    ("", "Home", "मुखपृष्ठम्"),
    ("stotras/", "Stotras", "स्तोत्राणि"),
    ("texts/", "Texts", "ग्रन्थाः"),
    ("lessons/", "Lessons", "पाठाः"),
    ("prahelikas/", "ప్రహేళికలు", ""),
    ("about/", "About", "परिचयः"),
    ("about/#contact", "Contact", "सम्पर्कः"),
    ("donate/", "Donate", "सहयोगः"),
]

# The original's menu also listed Songs, Articles, Worker Links, Blogs and FAQs.
# Every one of them pointed at home.php or "#" — announced, never published.
# They are named here rather than dropped, so nothing the school advertised
# disappears, and nothing pretends to work.
ANNOUNCED = ["Songs", "Articles", "Worker Links", "Blogs", "FAQs"]


def header(depth: int, active: str) -> str:
    r = rel(depth)
    links = []
    for href, label, _ in NAV:
        current = ' aria-current="page"' if href == active else ""
        sc = script_class(label)
        cls = f' class="{sc}"' if sc else ""
        links.append(f'<li><a href="{r}{href}"{current}{cls}>{e(label)}</a></li>')
    return f"""<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="{r}">
      <img src="{r}assets/img/logo.png" alt="" width="42" height="42">
      <span class="brand-text" data-no-lipi>
        <span class="brand-name">Samskrtam</span>
        <span class="brand-sub">{e(SITE_ORG)}</span>
      </span>
    </a>
    <nav class="nav" id="site-nav" aria-label="Main">
      <ul>{''.join(links)}</ul>
    </nav>
    <div class="header-tools tools-anchor">
      <button class="icon-btn" data-prefs-toggle aria-expanded="false" aria-controls="prefs-panel" aria-label="Reading preferences" type="button">{icon('text')}</button>
      <button class="icon-btn" data-theme-toggle aria-pressed="false" aria-label="Switch theme" type="button">{icon('sun', 'i-sun')}{icon('moon', 'i-moon')}</button>
      <button class="icon-btn nav-toggle" data-nav-toggle aria-expanded="false" aria-controls="site-nav" aria-label="Menu" type="button">{icon('menu')}</button>
      <div class="prefs" id="prefs-panel" hidden>
        <h5>Text size</h5>
        <div class="prefs__row">
          <button type="button" data-size="s" aria-pressed="false">A</button>
          <button type="button" data-size="m" aria-pressed="true">A</button>
          <button type="button" data-size="l" aria-pressed="false">A</button>
          <button type="button" data-size="xl" aria-pressed="false">A</button>
        </div>
        <h5>Script · लिपिः</h5>
        <div class="prefs__row">
          <button type="button" data-lipi-set="devanagari" aria-pressed="true" class="deva">देव</button>
          <button type="button" data-lipi-set="telugu" aria-pressed="false" class="telu">తెలు</button>
          <button type="button" data-lipi-set="iast" aria-pressed="false">IAST</button>
        </div>
        <p style="margin:0;font-size:.8rem;color:var(--ink-faint)">Converts every Devanāgarī passage on the page. Theme follows your device unless you pick one with the sun / moon button.</p>
      </div>
    </div>
  </div>
</header>"""


def footer(depth: int, home: dict) -> str:
    r = rel(depth)
    social = "".join(
        f'<a href="{e(s["href"])}" rel="noopener" target="_blank" aria-label="{e(s["name"].title())}">'
        f'<svg viewBox="0 0 24 24" aria-hidden="true">{SOCIAL_ICON.get(s["name"], SOCIAL_ICON["link"])}</svg></a>'
        for s in home.get("social", [])
    )
    useful = "".join(
        f'<li><a href="{e(s["href"])}" rel="noopener" target="_blank">{e(s["name"].title())}</a></li>'
        for s in home.get("social", [])
    )
    explore = "".join(
        f'<li><a href="{r}{href}">{e(label)}</a></li>'
        for href, label, _ in NAV[1:] if not href.startswith("about/#")
    )
    announced = "".join(
        f'<li><span class="footer-soon">{e(x)}</span></li>' for x in ANNOUNCED
    )
    return f"""<footer class="site-footer">
  <div class="wrap">
    <div class="footer-grid">
      <div>
        <img class="footer-seal" src="{r}assets/img/logo.png" alt="{e(SITE_ORG_LATIN)} seal" width="74" height="74">
        <p style="font-family:var(--font-deva);font-size:1.05rem;margin-bottom:.25rem">{e(SITE_ORG)}</p>
        <p style="font-size:.9rem">{e(SITE_ORG_LATIN)}</p>
        <p class="footer-motto">{e(MOTTO)}</p>
        <div class="social">{social}</div>
      </div>
      <div>
        <h4>Explore</h4>
        <ul>{explore}</ul>
      </div>
      <div>
        <h4>Useful links</h4>
        <ul>{useful}</ul>
      </div>
      <div>
        <h4>Announced</h4>
        <ul>{announced}</ul>
        <p style="font-size:.82rem;margin-top:.9rem">Listed on the school's menu,
          not yet published.</p>
      </div>
      <div>
        <h4>Get in touch</h4>
        <p>Please reach us at:</p>
        <ul>
          <li><a href="mailto:{EMAIL}">{EMAIL}</a></li>
          <li><a href="{BASE_URL}">samskrtam.info</a></li>
        </ul>
      </div>
    </div>
    <div class="footer-bottom">
      <span>Copyright © Svarvani Prakasha {YEAR}. All rights reserved by Svarvani.</span>
      <span>सफलतासिद्धिरस्तु · भाषाज्ञानानुग्रहप्राप्तिरस्तु</span>
    </div>
  </div>
</footer>"""


def crumbs(depth: int, trail: list[tuple[str, str]]) -> str:
    r = rel(depth)
    items = []
    for i, (href, label) in enumerate(trail):
        last = i == len(trail) - 1
        sc = script_class(label)
        cls = f' class="{sc}"' if sc else ""
        if last or href is None:
            items.append(f"<li><span{cls}>{e(label)}</span></li>")
        else:
            items.append(f'<li><a href="{r}{href}"{cls}>{e(label)}</a></li>')
    return f'<nav class="crumbs wrap" aria-label="Breadcrumb"><ol>{"".join(items)}</ol></nav>'


def page(*, path: str, depth: int, title: str, description: str, body: str,
         active: str = "", home: dict, head_extra: str = "") -> None:
    r = rel(depth)
    canonical = f"{BASE_URL}/{path.replace('index.html', '')}".rstrip("/") or BASE_URL
    full_title = title if title == SITE_NAME else f"{title} · {SITE_NAME}"
    markup = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{e(canonical)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(SITE_ORG_LATIN)}">
<meta property="og:title" content="{e(full_title)}">
<meta property="og:description" content="{e(description)}">
<meta property="og:image" content="{BASE_URL}/assets/img/logo.png">
<meta property="og:url" content="{e(canonical)}">
<meta name="twitter:card" content="summary">
<meta name="theme-color" content="#1b2a4a">
<link rel="icon" type="image/png" href="{r}assets/img/favicon.png">
<link rel="apple-touch-icon" href="{r}assets/img/logo.png">
<link rel="preload" href="{r}assets/fonts/Sanskrit2003.ttf" as="font" type="font/ttf" crossorigin>
<link rel="stylesheet" href="{r}assets/css/site.css">
<script>try{{var t=localStorage.getItem('svp:theme');if(t)document.documentElement.setAttribute('data-theme',t);
var s=localStorage.getItem('svp:size'),m={{s:.9,m:1,l:1.15,xl:1.3}};if(s&&m[s])document.documentElement.style.setProperty('--read-scale',m[s]);}}catch(e){{}}</script>
{head_extra}
</head>
<body>
<div class="progress" aria-hidden="true"></div>
{header(depth, active)}
<main id="main">
{body}
</main>
{footer(depth, home)}
<button class="icon-btn to-top" type="button" aria-label="Back to top">{icon('up')}</button>
<script src="{r}assets/js/lipi.js" defer></script>
<script src="{r}assets/js/site.js" defer></script>
</body>
</html>"""
    write(path, markup)


# --------------------------------------------------------------------------- #
# reusable fragments
# --------------------------------------------------------------------------- #
def video(yt: str, title: str, lazy: bool = True) -> str:
    if not yt:
        return ""
    if lazy:
        thumb = f"https://i.ytimg.com/vi/{e(yt)}/hqdefault.jpg"
        return (
            f'<div class="video video--lazy" data-yt="{e(yt)}" data-title="{e(title)}" '
            f'role="button" tabindex="0" aria-label="Play video: {e(title)}">'
            f'<img src="{thumb}" alt="" loading="lazy" width="480" height="360">'
            f'<span class="play" aria-hidden="true"></span></div>'
        )
    return (
        f'<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/{e(yt)}?rel=0" '
        f'title="{e(title)}" loading="lazy" allowfullscreen '
        f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"></iframe></div>'
    )


def filter_field(target_id: str, placeholder: str, count_id: str,
                 with_count: bool = True) -> str:
    """A search box. `with_count=False` when the live count is rendered
    elsewhere on the page, so the id stays unique."""
    count = (f'<p class="result-count" id="{count_id}" role="status" aria-live="polite"></p>'
             if with_count else "")
    return f"""<div class="field">
  {icon('search')}
  <label class="visually-hidden" for="q-{target_id}">{e(placeholder)}</label>
  <input id="q-{target_id}" type="search" placeholder="{e(placeholder)}" autocomplete="off"
         data-filter-input="{target_id}" data-filter-count="{count_id}">
  <button class="field__clear" type="button" aria-label="Clear search" hidden>×</button>
</div>
{count}"""


def layer_toolbar(scope: str, toggles: list[dict], extra_right: str = "") -> str:
    chips = "".join(
        f'<button class="chip deva" type="button" data-layer-toggle="{e(t["key"])}" '
        f'aria-pressed="true" style="--chip:var(--layer-{e(t["key"])}, var(--layer-extra))">'
        f'{e(t["label"])}</button>'
        for t in toggles
    )
    return f"""<div class="toolbar" data-layers="{e(scope)}">
  <div class="wrap toolbar__inner">
    <span class="toolbar__label">Show</span>
    <div class="chip-row">{chips}</div>
    <div class="toolbar__spacer"></div>
    <div class="cluster">
      <button class="btn btn--ghost btn--sm" type="button" data-layers-all>All</button>
      <button class="btn btn--ghost btn--sm" type="button" data-layers-none>मूलम् only</button>
      {extra_right}
    </div>
  </div>
</div>"""


def script_class(text: str) -> str:
    """Tag a string so the stylesheet stops tracking/uppercasing Indic glyphs."""
    if re.search(r"[\u0900-\u097F]", text or ""):
        return "deva"
    if re.search(r"[\u0C00-\u0C7F]", text or ""):
        return "telu"
    return ""


def page_hero(eyebrow: str, title: str, lede: str = "", deva: bool = True) -> str:
    cls = ' class="deva"' if deva else ""
    lede_html = f'<p class="hero__lede">{lede}</p>' if lede else ""
    eb = f"eyebrow {script_class(eyebrow)}".strip()
    return f"""<section class="section section--tight">
  <div class="wrap">
    <span class="{eb}">{e(eyebrow)}</span>
    <h1{cls}>{e(title)}</h1>
    {lede_html}
  </div>
</section>"""


# --------------------------------------------------------------------------- #
# 1. Home
# --------------------------------------------------------------------------- #
TILE_TARGETS = {
    "Stotras": ("stotras/", "स्तोत्राणि", "Chant along with recordings in Devanāgarī, Telugu and IAST."),
    "Text": ("texts/", "ग्रन्थाः", "Verse-by-verse commentaries, anvayas and reference tables."),
    "Lessons": ("lessons/", "पाठाः", "Structured video courses in Hindi, Telugu and English."),
    "Songs": (None, "गीतानि", "Coming soon."),
    "Interesting": ("prahelikas/", "ప్రహేళికలు", "Puzzles that make you look closely at a verse."),
    "faqs": (None, "प्रश्नाः", "Coming soon."),
}

WELCOME_META = {
    "sanskrit": ("संस्कृतम्", "deva", "var(--saffron)", "sa"),
    "telugu": ("తెలుగు", "telu", "var(--teal)", "te"),
    "english": ("English", "latn", "var(--layer-extra)", "en"),
}


def build_home(home: dict, texts: list, courses: list, stotras: list, prahelikas: dict) -> None:
    welcome_cards = ""
    for key in ("sanskrit", "telugu", "english"):
        text = home["welcome"].get(key)
        if not text:
            continue
        label, cls, colour, lang = WELCOME_META[key]
        welcome_cards += (
            f'<article class="welcome-card {cls}" style="--accent:{colour}">'
            f'<span class="welcome-card__ornament" aria-hidden="true">ॐ</span>'
            f"<h3>{e(label)}</h3><p lang=\"{lang}\">{e(text)}</p></article>"
        )

    videos = "".join(
        f'<div><h3 style="font-size:1.05rem;text-transform:uppercase;letter-spacing:.14em;'
        f'font-family:var(--font-sans);color:var(--ink-faint)">{e(v["title"].title())}</h3>'
        f'{video(v["youtube"], v["title"])}</div>'
        for v in home.get("videos", [])
    )

    tiles = ""
    for t in home.get("tiles", []):
        target, deva, blurb = TILE_TARGETS.get(t["label"], (None, "", ""))
        img = f'<div class="card__media"><img src="assets/img/{asset(Path(t["image"]).name)}" alt="" loading="lazy"></div>'
        inner = (
            f'{img}<div class="card__body">'
            f'<h3 class="card__title deva">{e(deva or t["label"])}</h3>'
            f'<p class="card__meta">{e(blurb)}</p></div>'
        )
        if target:
            tiles += f'<a class="card card--link" href="{target}">{inner}</a>'
        else:
            tiles += (
                f'<div class="card" aria-disabled="true" style="opacity:.62">{img}'
                f'<div class="card__body"><h3 class="card__title deva">{e(deva or t["label"])}</h3>'
                f'<p class="card__meta"><span class="badge badge--saffron">Coming soon</span></p></div></div>'
            )

    n_verses = len(load("hitopadesha")["verses"]) + len(load("subhashitas")["verses"])
    n_lessons = sum(len(c["lessons"]) for c in load("course_details"))
    n_dhatus = len(load("dhatupathah")["rows"])
    n_puzzles = sum(len(q["questions"]) for s in prahelikas["sets"] for q in s["puzzles"])

    stats = [
        (f"{n_verses}", "verses with word-split, anvaya and gloss", "texts/"),
        (f"{n_lessons}", "recorded lessons across 12 courses", "lessons/"),
        (f"{n_dhatus:,}", "dhātus in the धातुपाठविस्तरः table", "texts/dhatupathah/"),
        (f"{n_puzzles}", "prahelikā questions to test yourself", "prahelikas/"),
    ]
    stat_cards = "".join(
        f'<a class="card card--link" href="{href}"><div class="card__body">'
        f'<div style="font-size:var(--step-3);font-weight:700;color:var(--saffron);line-height:1">{e(n)}</div>'
        f'<p class="card__meta" style="margin:.4rem 0 0">{e(label)}</p></div></a>'
        for n, label, href in stats
    )

    body = f"""<section class="hero">
  <img class="hero__seal" src="assets/img/logo.png" alt="" aria-hidden="true" width="500" height="499">
  <div class="wrap hero__inner">
    <p class="hero__eyebrow">{e(SITE_ORG_LATIN)}</p>
    <h1>The light of <span style="color:var(--saffron)">Saṃskṛtam</span></h1>
    <p class="hero__motto deva">{e(MOTTO)}</p>
    <p class="hero__lede">A pāṭhaśālā for reading Śrīmadrāmāyaṇa, the Mahābhārata and the śāstras
      in the original — with word-splits, anvayas, glosses and recorded pronunciation for every verse.</p>
    <div class="cluster hero__cta">
      <a class="btn btn--accent" href="lessons/">Begin the lessons {icon('arrow')}</a>
      <a class="btn btn--ghost" href="texts/">{icon('book')} Enter the library</a>
    </div>
  </div>
</section>

<section class="section">
  <div class="wrap">
    <div class="section-head section-head--center">
      <span class="eyebrow">Namaste · नमस्ते · నమస్కారం</span>
      <h2>Welcome to <span style="color:var(--saffron)">SAMSKRTAM</span></h2>
      <p>The same welcome, in the three languages this school teaches in.</p>
    </div>
    <div class="welcome-grid">{welcome_cards}</div>
  </div>
</section>

<section class="section" style="background:var(--paper-subtle);border-block:1px solid var(--line-faint)">
  <div class="wrap">
    <div class="section-head"><span class="eyebrow">From the school</span><h2>Welcome video &amp; notice board</h2></div>
    <div class="grid grid--2">{videos}</div>
  </div>
</section>

<section class="section">
  <div class="wrap">
    <div class="section-head"><span class="eyebrow">Where to go</span><h2>Explore the pāṭhaśālā</h2></div>
    <div class="grid grid--tiles">{tiles}</div>
  </div>
</section>

<section class="section" style="padding-top:0">
  <div class="wrap">
    <div class="grid grid--tiles">{stat_cards}</div>
  </div>
</section>"""
    page(path="index.html", depth=0, title=SITE_NAME,
         description=home.get("meta_description", ""), body=body, active="", home=home)


# --------------------------------------------------------------------------- #
# 2. About
# --------------------------------------------------------------------------- #
def build_about(home: dict) -> None:
    """The original nav promised an About page but linked back to the home page.
    This one is written entirely out of the school's own words on the site."""
    vishnu = load("vishnu")
    contact_social = "".join(
        f'<a class="btn btn--ghost btn--sm" href="{e(x["href"])}" target="_blank" rel="noopener">'
        f'{e(x["name"].title())}</a>'
        for x in home.get("social", [])
    )
    signature = ""
    for para in vishnu.get("intro", []):
        if "उषाराणी" in para:
            signature = strip_tags(para)

    cards = ""
    for key in ("sanskrit", "telugu", "english"):
        text = home["welcome"].get(key)
        if not text:
            continue
        label, cls, colour, lang = WELCOME_META[key]
        cards += (
            f'<article class="welcome-card {cls}" style="--accent:{colour}">'
            f'<span class="welcome-card__ornament" aria-hidden="true">ॐ</span>'
            f"<h3>{e(label)}</h3><p lang=\"{lang}\">{e(text)}</p></article>"
        )

    body = crumbs(1, [("", "Home"), (None, "About")]) + f"""
{page_hero('परिचयः', 'About the pāṭhaśālā', 'Svarvāṇī Prakāśa · Sevā Nikuñjam — a school set up to study Saṃskṛtam with the aim of preserving culture and tradition.', deva=False)}
<section class="section" style="padding-top:0">
  <div class="wrap">
    <div class="welcome-grid">{cards}</div>
  </div>
</section>
<section class="section" style="padding-top:0">
  <div class="wrap-narrow">
    <div class="panel">
      <span class="eyebrow">What you will find here</span>
      <h2 style="margin-bottom:1rem">Reading the source, not a translation</h2>
      <p>Every text on this site is presented the way the school teaches it. A verse is
      first given as it stands (<span class="deva">मूलम्</span>), then split into its
      words (<span class="deva">पदविभागः</span>), re-ordered into natural prose
      (<span class="deva">अन्वयः</span>), glossed word by word
      (<span class="deva">प्रतिपदार्थः</span>) and finally restated in simple Sanskrit
      (<span class="deva">तात्पर्यम्</span>). Where a recording exists, you can hear the
      verse chanted with correct pronunciation.</p>
      <p>The commentaries are written in Sanskrit on purpose. Students who come through
      Saṃskṛta Bhāratī often stop at spoken Sanskrit; reading commentary in the language
      itself is what carries them into the original texts.</p>
      <ul class="link-list" style="margin-top:1.5rem">
        <li><a href="../texts/">{icon('book')} <span>The texts, commentaries and reference tables</span></a></li>
        <li><a href="../lessons/">{icon('play')} <span>Structured courses in Hindi, Telugu and English</span></a></li>
        <li><a href="../stotras/">{icon('play')} <span>Stotras with recordings in three scripts</span></a></li>
      </ul>
      {f'<p class="signature deva">{e(signature)}</p>' if signature else ''}
    </div>
    <section class="panel" id="contact" style="margin-top:1.75rem">
      <span class="eyebrow deva">सम्पर्कः</span>
      <h2 style="margin-bottom:1rem">Contact</h2>
      <p>Corrections and suggestions are welcome. If a reading looks wrong anywhere on
        this site, please say so — it will be fixed.</p>
      <ul class="link-list" style="margin-top:1.25rem">
        <li><a class="latn" href="mailto:{EMAIL}">{EMAIL}</a></li>
        <li><a class="latn" href="{BASE_URL}">{BASE_URL}</a></li>
      </ul>
      <div class="cluster" style="margin-top:1.25rem">{contact_social}</div>
    </section>
  </div>
</section>"""
    page(path="about/index.html", depth=1, title="About",
         description="Svarvāṇī Prakāśa · Sevā Nikuñjam — a Sanskrit pāṭhaśālā teaching students to read Rāmāyaṇa, Mahābhārata and the śāstras in the original.",
         body=body, active="about/", home=home)


# --------------------------------------------------------------------------- #
# 3. Stotras
# --------------------------------------------------------------------------- #
SCRIPT_LABEL = {"devanagari": "देवनागरी", "telugu": "తెలుగు", "iast": "IAST"}
SCRIPT_CLASS = {"devanagari": "deva", "telugu": "telu", "iast": "latn"}


def build_stotras(stotras: list, details: list, home: dict) -> None:
    detail_by_href = {d["id"]: d for d in details}

    chips = "".join(
        f'<button class="chip {SCRIPT_CLASS[k]}" type="button" data-script-toggle="{k}" aria-pressed="true" '
        f'style="--chip:var(--layer-{"moolam" if k == "devanagari" else "pada" if k == "telugu" else "prati"})">'
        f'{e(v)}</button>'
        for k, v in SCRIPT_LABEL.items()
    )

    cards = ""
    for st in stotras:
        did = re.search(r"id=(\d+)", st.get("detail", "") or "")
        detail = detail_by_href.get(did.group(1)) if did else None
        href = f"{detail['slug']}/" if detail else ""
        for v in st["versions"]:
            cls = SCRIPT_CLASS.get(v["script"], "latn")
            script_label = SCRIPT_LABEL.get(v["script"], "")
            script_cls = SCRIPT_CLASS.get(v["script"], "latn")
            read = (f'<a class="stotra__read" href="{e(href)}">Read the text {icon("arrow")}</a>'
                    if href else "")
            cards += f"""<article class="card stotra" data-script="{e(v['script'])}"
              data-search="{search_key(st['title'], st['keywords'], v['label'], script_label)}">
              <header class="stotra__head">
                <span class="stotra__script {script_cls}">{e(script_label)}</span>
                <h3 class="stotra__name">{e(st['title'])}</h3>
              </header>
              {video(v['youtube'], v['label'])}
              <footer class="stotra__foot">{read}</footer>
            </article>"""

    body = crumbs(1, [("", "Home"), (None, "Stotras")]) + f"""
{page_hero('स्तोत्राणि', 'Stotras', 'Learn to chant with correct pronunciation. Each stotra is recorded once for every script, and the text pages carry a word-by-word English meaning.', deva=False)}
<div class="toolbar" data-scripts>
  <div class="wrap toolbar__inner">
    <span class="toolbar__label">Script</span>
    <div class="chip-row">{chips}</div>
    <div class="toolbar__spacer"></div>
    <div class="toolbar__search">{filter_field('stotra-list', 'Filter stotras…', 'stotra-count')}</div>
  </div>
</div>
<section class="section" style="padding-top:0">
  <div class="wrap">
    <div class="grid grid--3" id="stotra-list">{cards}
      <p class="empty-state" data-empty hidden>No stotra matches that search.</p>
    </div>
  </div>
</section>"""
    page(path="stotras/index.html", depth=1, title="Stotras",
         description="Sanskrit stotras with recordings in Devanāgarī, Telugu and IAST, plus word-by-word meaning.",
         body=body, active="stotras/", home=home)

    for d in details:
        tabs = "".join(
            f'<button class="chip" type="button" data-layer-toggle="{e(s["id"])}" aria-pressed="true" '
            f'style="--chip:var(--layer-{"moolam" if i == 0 else "pada" if i == 1 else "prati"})">'
            f'{e(s["heading"] or s["tab"])}</button>'
            for i, s in enumerate(d["sections"])
        )
        sections = "".join(
            f'<section class="layer layer--plain" data-layer="{e(s["id"])}" style="margin-bottom:2.5rem">'
            f'<div class="chapter-head"><h3 class="latn">{e(s["heading"] or s["tab"])}</h3></div>'
            f'<div class="stanzas">{render_stanzas(s["body"])}</div></section>'
            for s in d["sections"]
        )
        sec_body = crumbs(2, [("", "Home"), ("stotras/", "Stotras"), (None, d["title"])]) + f"""
{page_hero('स्तोत्रम्', d['title'], '', deva=False)}
<section class="section" style="padding-top:0">
  <div class="wrap-narrow">
    {f'<div class="panel" style="margin-bottom:1.75rem"><span class="eyebrow">From the teacher</span><div class="latn stotra__intro">{d["intro"]}</div></div>' if d.get('intro') else ''}
    {video(d.get('youtube', ''), d['title'])}
  </div>
</section>
<div class="toolbar" data-layers="stotra-{e(d['id'])}">
  <div class="wrap toolbar__inner">
    <span class="toolbar__label">Show</span>
    <div class="chip-row">{tabs}</div>
  </div>
</div>
<section class="section" style="padding-top:0">
  <div class="wrap-narrow">{sections}</div>
</section>"""
        page(path=f"stotras/{d['slug']}/index.html", depth=2, title=d["title"],
             description=f"{d['title']} — full text with hyphenated reading and word-by-word English meaning.",
             body=sec_body, active="stotras/", home=home)


# --------------------------------------------------------------------------- #
# 4. Texts index + corpora
# --------------------------------------------------------------------------- #
TEXT_ROUTES = {
    "hitopadesha.php": "hitopadesha",
    "subhashitas.php": "subhashitas",
    "hitopadesha-adhyayana.php": "adhyayanam",
    "dhatupathah.php": "dhatupathah",
    "raamayan.php": "raamayana",
    "gita.php": "gita",
    "sulakshana.php": "sulakshana",
    "saritsaagara.php": "saritsagara",
    "vishnu.php": "vishnusahasranama",
}

TEXT_BLURB = {
    "hitopadesha": "Every verse split, re-ordered, glossed and paraphrased — with recorded chanting.",
    "subhashitas": "A subhāṣita a day, with sentence practice and questions.",
    "adhyayanam": "The whole Hitopadeśa with notes, analysis and an English rendering.",
    "dhatupathah": "A searchable dhātu table from Bṛhad-Dhāturūpāvalī, with every parameter.",
    "raamayana": "A sarga-by-sarga index of everything that happens in the Rāmāyaṇa.",
    "gita": "The Gītā re-set as running prose, chapter by chapter, speaker by speaker.",
    "sulakshana": "Sulakṣaṇā's story in anvaya order, with meanings in brackets.",
    "saritsagara": "The rivers-and-ocean dialogue from the Śāntiparva, in anvaya order.",
    "vishnusahasranama": "The phalaśruti of the Viṣṇusahasranāma, re-ordered for reading.",
}


# The texts index used the school's raster cover art — wooden planks with
# flower clipart that only repeat the title the card already carries. It is
# drawn in CSS instead. Flip this to True to go back to the original plates;
# the artwork is still in original-site/ and dist/assets/img/ either way.
USE_ORIGINAL_TEXT_COVERS = False

# one pigment per text, so the library reads as a shelf of bound volumes
COVER_PIGMENTS = [
    "#1e293b",  # iron-gall
    "#0c5c55",  # mineral emerald
    "#4a1d73",  # deep jamun
    "#7d1c23",  # madder
    "#8a4008",  # burnt sienna
    "#1b3a8f",  # indigo
    "#2f3d33",  # olive slate
    "#12494a",  # verdigris
    "#5c2410",  # rust
]


def cover(title: str, index: int, script: str = "deva") -> str:
    """An illuminated cover drawn in CSS: jālī ground, brass keyline, the
    Sanskrit title engraved in gold. No raster, no request, sharp at any DPI.

    The title lives here rather than being repeated underneath — the cover is
    the volume's face, the line below it is the catalogue entry."""
    pigment = COVER_PIGMENTS[index % len(COVER_PIGMENTS)]
    return (
        f'<div class="cover" style="--cover:{pigment}">'
        f'<div><h3 class="cover__title deva">{e(title)}</h3>'
        f'<span class="cover__rule" aria-hidden="true"></span></div></div>'
    )


TEXT_IMAGES: dict[str, str] = {}


def text_plate(route: str) -> str:
    """The school's own cover for this text, mounted as a plate.

    The index carries drawn covers now, but the artwork is the pāṭhaśālā's own
    work — it belongs on the text it was made for, not thrown away."""
    img = TEXT_IMAGES.get(route)
    if not img:
        return ""
    return (f'<figure class="text-plate"><img src="../../assets/img/{asset(img)}" '
            f'alt="" loading="lazy"></figure>')


def build_texts_index(texts: list, home: dict) -> None:
    groups = ""
    n = 0
    for g in texts:
        items = ""
        for it in g["items"]:
            route = TEXT_ROUTES.get(it["href"])
            if not route:
                continue
            TEXT_IMAGES[route] = Path(it["image"]).name
            if USE_ORIGINAL_TEXT_COVERS:
                img = asset(Path(it["image"]).name)
                face = (f'<div class="card__media"><img src="../assets/img/{img}" '
                        f'alt="" loading="lazy"></div>'
                        f'<div class="card__body">'
                        f'<h3 class="card__title deva">{e(it["title"])}</h3>')
            else:
                face = f'{cover(it["title"], n)}<div class="card__body">'
            items += (
                f'<a class="card card--link" href="{route}/">{face}'
                f'<p class="card__meta">{e(TEXT_BLURB.get(route, ""))}</p></div></a>'
            )
            n += 1
        groups += f"""<section class="section section--tight">
  <div class="wrap">
    <div class="section-head"><span class="eyebrow">{e(g['title'])}</span></div>
    <div class="grid grid--3">{items}</div>
  </div>
</section>"""

    body = crumbs(1, [("", "Home"), (None, "Texts")]) + f"""
{page_hero('ग्रन्थाः', 'Text contents', 'Commentaries, anvayas and reference tables — the working library of the pāṭhaśālā.', deva=False)}
{groups}"""
    page(path="texts/index.html", depth=1, title="Texts",
         description="Sanskrit texts with verse-by-verse commentary, anvayas and reference tables.",
         body=body, active="texts/", home=home)


LAYER_ORDER = ["moolam", "pada", "anvaya", "prati", "taatparyam",
               "hindyartham", "vyakyaa", "prasnaa", "audio"]


def build_verse_corpus(name: str, route: str, home: dict) -> None:
    data = load(name)
    toggles = [t for t in data["toggles"] if t["key"] != "audio"]

    have_audio = 0
    verses_html = []
    next_id = unique_ids("v")
    for v in data["verses"]:
        vid = next_id(v["id"])
        rows = ""
        keys = [k for k in LAYER_ORDER if k in v["fields"]]
        keys += [k for k in v["fields"] if k not in LAYER_ORDER]
        for k in keys:
            f = v["fields"][k]
            rows += (
                f'<div class="layer" data-layer="{e(k)}">'
                f'<div class="layer__label">{e(f["label"])}</div>'
                f'<div class="layer__value">{set_register(k, f["value"])}</div></div>'
            )
        audio_html = ""
        if v.get("audio") and media_exists(v["audio"]):
            have_audio += 1
            audio_html = (
                f'<div class="layer" data-layer="audio">'
                f'<div class="layer__label">उच्चारणम्</div>'
                f'<div class="layer__value"><audio controls preload="none" '
                f'src="../../assets/{asset(v["audio"])}"></audio></div></div>'
            )
        tools = "".join(
            f'<button class="chip btn--sm deva" type="button" data-verse-toggle="{e(k)}" '
            f'aria-pressed="true" style="--chip:var(--layer-{e(k)}, var(--layer-extra));font-size:.78rem;padding:.2rem .6rem">'
            f'{e(v["fields"][k]["label"])}</button>'
            for k in keys[1:4]
        )
        verses_html.append(f"""<article class="verse" id="{vid}" data-search>
  <div class="verse__head">
    {folio(v['id'])}
    <div class="verse__tools">{tools}
      <button class="icon-btn" type="button" data-copy-link="{vid}" aria-label="Copy link to this verse">{icon('link')}</button>
    </div>
  </div>
  <div class="verse__body">{rows}{audio_html}</div>
</article>""")

    audio_toggle = ""
    if have_audio:
        toggles = toggles + [{"key": "audio", "label": "उच्चारणम्"}]

    intro = ""
    if data.get("intro"):
        first = data["intro"][0]
        rest = "".join(f'<p class="deva scripture">{p}</p>' for p in data["intro"][1:])
        intro = f"""<div class="panel" style="margin-bottom:1.75rem">
  <p class="deva scripture">{first}</p>
  {f'<details class="expander"><summary>More · अधिकम्</summary>{rest}</details>' if rest else ''}
</div>"""

    audio_note = ""
    missing = sum(1 for v in data["verses"] if v.get("audio")) - have_audio
    if missing > 0:
        audio_note = (
            f'<div class="note" style="margin-bottom:1.5rem"><strong>Recordings.</strong> '
            f'{have_audio} of {have_audio + missing} verses currently have a chanting recording available; '
            f'the player is shown only where the audio exists.</div>'
        )

    body = crumbs(2, [("", "Home"), ("texts/", "Texts"), (None, data["title"])]) + f"""
{page_hero('श्लोकव्याख्यानम्', data['title'])}
<section class="section" style="padding-top:0">
  <div class="wrap">{text_plate(route)}{intro}{audio_note}</div>
</section>
{layer_toolbar(name, toggles, f'<div class="toolbar__search">{filter_field(route + "-list", "Search verses…", route + "-count")}</div>')}
<section class="section" style="padding-top:0">
  <div class="wrap" id="{route}-list">
    {''.join(verses_html)}
    <p class="empty-state" data-empty hidden>No verse matches that search.</p>
  </div>
</section>"""
    page(path=f"texts/{route}/index.html", depth=2, title=data["title"],
         description=f"{data['title']} — {len(data['verses'])} verses with word-split, anvaya, gloss and paraphrase.",
         body=body, active="texts/", home=home)


# --------------------------------------------------------------------------- #
# 5. Adhyayanam (paginated)
# --------------------------------------------------------------------------- #
ADHY_LABEL = {
    "moolam": "मूलम्",
    "pada": "पदविभागः",
    "tippani": "टिप्पणी",
    "vishleshanam": "विश्लेषणम्",
    "english": "आङ्ग्लार्थः",
}
PER_PAGE = 120

# the five books of the Hitopadeśa, in the order the XML carries them
ADHY_SLUGS = ["prastavika", "mitralabhah", "suhrdbhedah", "vigrahah", "sandhih"]


def adhy_slug(index: int, title: str) -> str:
    if 0 <= index < len(ADHY_SLUGS):
        return ADHY_SLUGS[index]
    return slug(title, f"section-{index}")


def build_adhyayanam(home: dict) -> None:
    data = load("adhyayanam")
    toggles = [{"key": k, "label": v} for k, v in ADHY_LABEL.items()]

    routes: list[tuple[str, str, int, int]] = []  # (path, title, section index, page)
    for si, sec in enumerate(data["sections"]):
        total = max(1, math.ceil(len(sec["groups"]) / PER_PAGE))
        for p in range(1, total + 1):
            base = f"texts/adhyayanam/{adhy_slug(si, sec['title'])}"
            path = f"{base}/index.html" if p == 1 else f"{base}/page-{p}/index.html"
            routes.append((path, sec["title"], si, p))

    section_nav = ""
    for si, sec in enumerate(data["sections"]):
        section_nav += f'<a href="../{adhy_slug(si, sec["title"])}/">{e(sec["title"])}</a>'

    for path, title, si, pnum in routes:
        sec = data["sections"][si]
        depth = path.count("/")
        total = max(1, math.ceil(len(sec["groups"]) / PER_PAGE))
        chunk = sec["groups"][(pnum - 1) * PER_PAGE: pnum * PER_PAGE]

        cards = []
        next_id = unique_ids("g")
        for g in chunk:
            gid = next_id(g["ident"])
            rows = ""
            for key, label in ADHY_LABEL.items():
                lines = g.get(key)
                if not lines:
                    continue
                cls = "latn" if key in ("english", "vishleshanam") else "deva"
                value = "<br>".join(e(x) for x in lines)
                if key == "moolam":
                    value = "".join(f'<span class="pada">{e(x)}</span>' for x in lines)
                rows += (
                    f'<div class="layer" data-layer="{key}">'
                    f'<div class="layer__label">{e(label)}</div>'
                    f'<div class="layer__value {cls}">{value}</div></div>'
                )
            cards.append(f"""<article class="verse" id="{gid}" data-search>
  <div class="verse__head">
    {folio(g['ident'])}
    <span class="badge" style="font-size:.65rem">{e(g['type'])}</span>
    <div class="verse__tools">
      <button class="icon-btn" type="button" data-copy-link="{gid}" aria-label="Copy link">{icon('link')}</button>
    </div>
  </div>
  <div class="verse__body">{rows}</div>
</article>""")

        pager = ""
        if total > 1:
            base = f"{rel(1)}"
            links = []
            for p in range(1, total + 1):
                if p == pnum:
                    links.append(f'<span aria-current="page">{p}</span>')
                else:
                    target = "../" if p == 1 else f"../page-{p}/"
                    if pnum == 1:
                        target = "./" if p == 1 else f"page-{p}/"
                    links.append(f'<a href="{target}">{p}</a>')
            pager = f'<nav class="pager" aria-label="Pages">{"".join(links)}</nav>'

        nav_prefix = "../" if pnum == 1 else "../../"
        nav = "".join(
            f'<a href="{nav_prefix}{adhy_slug(i, s["title"])}/">{e(s["title"])}</a>'
            for i, s in enumerate(data["sections"])
        )

        crumb_depth = depth
        body = crumbs(crumb_depth, [("", "Home"), ("texts/", "Texts"), (None, data["title"])]) + f"""
{page_hero('अध्ययनम्', f"{data['title']} · {title}", f'Section {si + 1} of {len(data["sections"])} — page {pnum} of {total}.', deva=False)}
<section class="section" style="padding-top:0">
  <div class="wrap"><div class="jumpnav">{nav}</div></div>
</section>
{layer_toolbar('adhyayanam', toggles, f'<div class="toolbar__search">{filter_field("adhy-list", "Search this section…", "adhy-count")}</div>')}
<section class="section" style="padding-top:0">
  <div class="wrap" id="adhy-list">
    {''.join(cards)}
    <p class="empty-state" data-empty hidden>Nothing on this page matches that search.</p>
  </div>
  {pager}
</section>"""
        page(path=path, depth=crumb_depth, title=f"{data['title']} · {title}",
             description=f"{data['title']} — {title}, with word-split, notes, analysis and English meaning.",
             body=body, active="texts/", home=home)

    # landing page redirects to the first section
    listing = "".join(
        f'<a class="card card--link" href="{adhy_slug(i, s["title"])}/"><div class="card__body">'
        f'<h3 class="card__title deva">{e(s["title"])}</h3>'
        f'<p class="card__meta">{len(s["groups"])} entries</p></div></a>'
        for i, s in enumerate(data["sections"])
    )
    body = crumbs(2, [("", "Home"), ("texts/", "Texts"), (None, data["title"])]) + f"""
{page_hero('अध्ययनम्', data['title'], 'The complete Hitopadeśa, entry by entry, with word-splits, notes (टिप्पणी), analysis and an English rendering.', deva=False)}
<section class="section" style="padding-top:0">
  <div class="wrap">{text_plate('adhyayanam')}<div class="grid grid--3">{listing}</div></div>
</section>"""
    page(path="texts/adhyayanam/index.html", depth=2, title=data["title"],
         description="The complete Hitopadeśa with word-splits, notes, analysis and English meaning.",
         body=body, active="texts/", home=home)


# --------------------------------------------------------------------------- #
# 6. Dhātupāṭha
# --------------------------------------------------------------------------- #
# how each column of the dhātu table is set: a key for the mobile card layout
# and the treatment its value gets
# Only the three values that read as grammatical categories get a badge; the
# rest are coloured by column position, which costs nothing in markup — at
# 2 101 rows a wrapper span per cell is half a megabyte of nothing.
DHATU_BADGE = {0: "dhatu", 3: "tag tag--gana", 4: "tag tag--karma", 6: "tag tag--pada"}


def build_dhatupathah(home: dict) -> None:
    data = load("dhatupathah")
    labels = data["columns"]
    head = "".join(f'<th scope="col">{e(c)}</th>' for c in labels)

    ganas: dict[str, int] = {}
    for r in data["rows"]:
        g = r[3] if len(r) > 3 else ""
        if g:
            ganas[g] = ganas.get(g, 0) + 1

    rows = []
    for r in data["rows"]:
        cells = ""
        for i, value in enumerate(r):
            inner = e(value)
            cls = DHATU_BADGE.get(i)
            if value and cls:
                inner = f'<span class="{cls}">{inner}</span>'
            cells += f"<td>{inner}</td>"
        gana = r[3] if len(r) > 3 else ""
        rows.append(f'<tr data-search data-facet-gana="{e(gana)}">{cells}</tr>')

    # Under 768px every cell needs its own label. Carrying that as a data
    # attribute would repeat the column headings 18 909 times, so the labels
    # are stamped once, by column position.
    col_css = "\n".join(
        f'  table.data td:nth-child({i + 1})::before {{ content: "{c}"; }}'
        for i, c in enumerate(labels)
    )
    head_extra = (
        "<style>\n@media (max-width: 768px) {\n" + col_css + "\n}\n</style>"
    )

    facets = "".join(
        f'<button class="chip" type="button" data-facet="gana" data-facet-value="{e(g)}" '
        f'aria-pressed="false" style="--chip:var(--teal)">{e(g)} '
        f'<span class="card__meta" style="margin-left:.35rem">{n}</span></button>'
        for g, n in sorted(ganas.items(), key=lambda kv: -kv[1])
    )

    note = "".join(f'<p style="margin-bottom:.5rem">{p}</p>' for p in data["note"])
    body = crumbs(2, [("", "Home"), ("texts/", "Texts"), (None, data["title"])]) + f"""
{page_hero('सन्दर्भः', data['title'])}
<section class="section" style="padding-top:0">
  <div class="wrap">
    {text_plate('dhatupathah')}
    <div class="panel" style="margin-bottom:1.75rem">{note}</div>
  </div>
</section>
<div class="toolbar" data-facets="dhatu-table">
  <div class="wrap toolbar__inner">
    <span class="toolbar__label deva">गणः</span>
    <div class="chip-row">
      <button class="chip" type="button" data-facet="gana" data-facet-value="" aria-pressed="true"
              style="--chip:var(--saffron)">All</button>
      {facets}
    </div>
    <div class="cluster">
      <div class="toolbar__search">{filter_field('dhatu-table', 'Search dhātu, meaning, form…', 'dhatu-count', with_count=False)}</div>
    </div>
  </div>
</div>
<section class="section" style="padding-top:0">
  <div class="wrap">
    <div class="table-wrap" id="dhatu-table" data-highlight>
      <table class="data">
        <thead><tr>{head}</tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    <p class="empty-state" data-empty hidden>No dhātu matches that search.</p>
    <p class="result-count" id="dhatu-count" role="status" aria-live="polite"></p>
  </div>
</section>"""
    page(path="texts/dhatupathah/index.html", depth=2, title=data["title"],
         description=f"{data['title']} — a searchable table of {len(data['rows'])} Sanskrit dhātus with gaṇa, transitivity, iṭ and forms.",
         body=body, active="texts/", home=home, head_extra=head_extra)


# --------------------------------------------------------------------------- #
# 7. Prose corpora
# --------------------------------------------------------------------------- #
def verse_cards(verses: list, prefix: str) -> str:
    out = []
    next_id = unique_ids(prefix)
    for v in verses:
        vid = next_id(v["id"])
        rows = ""
        for k in [x for x in LAYER_ORDER if x in v["fields"]]:
            f = v["fields"][k]
            rows += (
                f'<div class="layer" data-layer="{e(k)}">'
                f'<div class="layer__label">{e(f["label"])}</div>'
                f'<div class="layer__value">{set_register(k, f["value"])}</div></div>'
            )
        out.append(
            f'<article class="verse" id="{vid}" data-search>'
            f'<div class="verse__head">{folio(v["id"])}'
            f'<div class="verse__tools"><button class="icon-btn" type="button" data-copy-link="{vid}" '
            f'aria-label="Copy link to this verse">{icon("link")}</button></div></div>'
            f'<div class="verse__body">{rows}</div></article>'
        )
    return "".join(out)


def build_pre_corpus(name: str, route: str, eyebrow: str, home: dict, jump: bool = False) -> None:
    data = load(name)
    nav = ""
    if jump:
        nav = '<div class="jumpnav">' + "".join(
            f'<a href="#{e(s["id"])}">{e(s["title"])}</a>' for s in data["sections"]
        ) + "</div>"

    blocks = ""
    for s in data["sections"]:
        heading = f"<h3>{e(s['title'])}</h3>" if s["title"] else ""
        verses = s.get("verses") or []
        if verses and not s["parts"]:
            # a section built from verse blocks rather than running prose
            blocks += (
                f'<section id="{e(s["id"])}" style="margin-bottom:1.5rem">'
                f'<div class="chapter-head">{heading}</div>'
                f'{verse_cards(verses, s["id"])}</section>'
            )
            continue
        first, rest = s["parts"][0], s["parts"][1:]
        more = ""
        if rest:
            inner = "".join(f"<pre>{linkify(e(p))}</pre>" for p in rest)
            more = f'<details class="expander"><summary>Read the rest · अधिकम्</summary>{inner}</details>'
        blocks += (
            f'<section class="scroll-block" id="{e(s["id"])}">{heading}'
            f"<pre>{linkify(e(first))}</pre>{more}</section>"
        )

    intro = ""
    if data.get("intro"):
        intro = '<div class="panel" style="margin-bottom:1.75rem">' + "".join(
            f'<p class="deva scripture">{p}</p>' for p in data["intro"]
        ) + "</div>"

    body = crumbs(2, [("", "Home"), ("texts/", "Texts"), (None, data["title"])]) + f"""
{page_hero(eyebrow, data['title'])}
<section class="section" style="padding-top:0">
  <div class="wrap">{text_plate(route)}{intro}{nav}{blocks}</div>
</section>"""
    page(path=f"texts/{route}/index.html", depth=2, title=data["title"],
         description=f"{data['title']} — Sanskrit text arranged in anvaya order with meanings in brackets.",
         body=body, active="texts/", home=home)


# --------------------------------------------------------------------------- #
# 8. Gītā
# --------------------------------------------------------------------------- #
def build_gita(home: dict) -> None:
    data = load("gita")
    chips = "".join(
        f'<button class="chip deva" type="button" data-speaker-toggle="{e(s["key"])}" aria-pressed="true" '
        f'style="--chip:{{krishna:"#1e5fa8",arjuna:"#b8322f",sanjaya:"#0f766e",dritarashtra:"#7a4bb8"}}">'
        f'{e(s["label"])}</button>'
        for s in data["speakers"]
    )
    # inline style above needs literal colours, not a JS object
    colours = {"krishna": "#1e5fa8", "arjuna": "#b8322f", "sanjaya": "#0f766e", "dritarashtra": "#7a4bb8"}
    chips = "".join(
        f'<button class="chip deva" type="button" data-speaker-toggle="{e(s["key"])}" aria-pressed="true" '
        f'style="--chip:{colours.get(s["key"], "var(--gold)")}">'
        f'{e(s["label"])}</button>'
        for s in data["speakers"]
    )

    nav = '<div class="jumpnav">' + "".join(
        f'<a href="#{e(c["id"])}">{e(c["title"])}</a>' for c in data["chapters"]
    ) + "</div>"

    body_blocks = ""
    for c in data["chapters"]:
        speeches = ""
        for b in c["blocks"]:
            avatar = ""
            if b.get("avatar"):
                avatar = f'<img class="speech__avatar" src="../../assets/img/{asset(Path(b["avatar"]).name)}" alt="" loading="lazy" width="54" height="54">'
            else:
                avatar = '<span class="speech__avatar" aria-hidden="true"></span>'
            speeches += (
                f'<article class="speech" data-speaker="{e(b["speaker"])}">{avatar}'
                f'<div><p class="speech__name">{e(b["speaker_label"])}</p>'
                f'<p class="speech__text">{e(b["text"])}</p></div></article>'
            )
        body_blocks += (
            f'<div class="chapter-head" id="head-{e(c["id"])}"><h3 id="{e(c["id"])}">{e(c["title"])}</h3></div>'
            f'<div data-chapter="{e(c["id"])}">{speeches}</div>'
        )

    intro = ""
    if data.get("intro"):
        intro = '<div class="panel" style="margin-bottom:1.75rem">' + "".join(
            f'<p class="latn">{p}</p>' for p in data["intro"]
        ) + "</div>"

    body = crumbs(2, [("", "Home"), ("texts/", "Texts"), (None, data["title"])]) + f"""
{page_hero('अन्वयः', data['title'])}
<section class="section" style="padding-top:0"><div class="wrap">{text_plate('gita')}{intro}</div></section>
<div class="toolbar" data-speakers>
  <div class="wrap toolbar__inner">
    <span class="toolbar__label">Speaker</span>
    <div class="chip-row">{chips}</div>
  </div>
</div>
<section class="section" style="padding-top:0">
  <div class="wrap">{nav}{body_blocks}</div>
</section>"""
    page(path="texts/gita/index.html", depth=2, title=data["title"],
         description="The Bhagavad Gītā re-set as running Sanskrit prose in anvaya order, chapter by chapter.",
         body=body, active="texts/", home=home)


def build_vishnu(home: dict) -> None:
    data = load("vishnu")
    speeches = ""
    for b in data["blocks"]:
        avatar = (
            f'<img class="speech__avatar" src="../../assets/img/{asset(Path(b["avatar"]).name)}" alt="" loading="lazy" width="54" height="54">'
            if b.get("avatar") else '<span class="speech__avatar" aria-hidden="true"></span>'
        )
        speeches += (
            f'<article class="speech" data-speaker="{e(b["speaker"])}">{avatar}'
            f'<div><p class="speech__text">{linkify(e(b["text"]))}</p></div></article>'
        )
    sections = ""
    for s in data["sections"]:
        first, rest = s["parts"][0], s["parts"][1:]
        more = ""
        if rest:
            inner = "".join(f"<pre>{linkify(e(p))}</pre>" for p in rest)
            more = f'<details class="expander"><summary>Read the rest · अधिकम्</summary>{inner}</details>'
        heading = f"<h3>{e(s['title'])}</h3>" if s["title"] else ""
        sections += (
            f'<section class="scroll-block" id="{e(s["id"])}">{heading}'
            f"<pre>{linkify(e(first))}</pre>{more}</section>"
        )
    intro = '<div class="panel" style="margin-bottom:1.75rem">' + "".join(
        f'<p class="deva scripture">{p}</p>' for p in data.get("intro", [])
    ) + "</div>" if data.get("intro") else ""

    body = crumbs(2, [("", "Home"), ("texts/", "Texts"), (None, data["title"])]) + f"""
{page_hero('अन्वयक्रमे', data['title'])}
<section class="section" style="padding-top:0">
  <div class="wrap">{text_plate('vishnusahasranama')}{intro}{speeches}{sections}</div>
</section>"""
    page(path="texts/vishnusahasranama/index.html", depth=2, title=data["title"],
         description="The phalaśruti of the Viṣṇusahasranāma re-ordered into anvaya sequence for reading.",
         body=body, active="texts/", home=home)


# --------------------------------------------------------------------------- #
# 9. Lessons
# --------------------------------------------------------------------------- #
LANG_NATIVE = {"hindi": "हिन्दी", "telugu": "తెలుగు", "english": "English"}


def build_lessons(courses: list, details: list, home: dict) -> None:
    by_key: dict[tuple[str, str], dict] = {(d["key"], d["lang"]): d for d in details}

    # the original repeats the Amarakośa card twice (second one mislabelled
    # "Devavan" but pointing at the same course) - keep one.
    seen: set[tuple[str, ...]] = set()
    unique = []
    for c in courses:
        sig = (c["key"], tuple(l["lang"] for l in c["languages"]))
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(c)

    cards = ""
    for c in unique:
        langs = ""
        for l in c["languages"]:
            d = by_key.get((c["key"], l["lang"]))
            if not d:
                continue
            label = e(LANG_NATIVE.get(l["lang"], l["lang"]))
            if d["lessons"]:
                langs += (
                    f'<a class="btn btn--ghost btn--sm" href="{e(c["key"])}-{e(l["lang"])}/">'
                    f'{label} <span class="card__meta">· {len(d["lessons"])}</span></a>'
                )
            else:
                langs += (
                    f'<span class="btn btn--muted btn--sm" title="No lessons recorded yet">'
                    f'{label} <span class="card__meta">· soon</span></span>'
                )
        taught = sum(len(by_key[(c["key"], l["lang"])]["lessons"])
                     for l in c["languages"] if (c["key"], l["lang"]) in by_key)
        cards += f"""<article class="card course" data-search="{search_key(c['title'], c['key'], c['keywords'], [LANG_NATIVE.get(l['lang'], '') for l in c['languages']])}">
  <div class="card__media"><img src="../assets/img/{asset(Path(c["image"]).name)}" alt="" loading="lazy"></div>
  <div class="card__body">
    <h3 class="card__title deva">{e(c['title'])}</h3>
    <p class="course__count">{taught} recorded {'lesson' if taught == 1 else 'lessons'}</p>
    <div class="cluster course__langs">{langs}</div>
  </div>
</article>"""

    total = sum(len(d["lessons"]) for d in details)
    body = crumbs(1, [("", "Home"), (None, "Lessons")]) + f"""
{page_hero('पाठाः', 'Courses', f'{total} recorded lessons across {len(unique)} courses, taught in Hindi, Telugu and English. Each lesson links its video and, where one exists, a downloadable worksheet.', deva=False)}
<section class="section" style="padding-top:0">
  <div class="wrap">
    <div style="max-width:520px;margin-bottom:1.5rem">{filter_field('course-list', 'Filter courses…', 'course-count')}</div>
    <div class="grid grid--3" id="course-list">{cards}
      <p class="empty-state" data-empty hidden>No course matches that search.</p>
    </div>
  </div>
</section>"""
    page(path="lessons/index.html", depth=1, title="Lessons",
         description="Structured Sanskrit video courses in Hindi, Telugu and English, with worksheets.",
         body=body, active="lessons/", home=home)

    for d in details:
        rows = ""
        for i, lesson in enumerate(d["lessons"], 1):
            actions = ""
            if lesson["youtube"]:
                actions += (
                    f'<a class="btn btn--accent btn--sm" target="_blank" rel="noopener" '
                    f'href="https://www.youtube.com/watch?v={e(lesson["youtube"])}">{icon("play")} Watch</a>'
                )
            pdf = lesson.get("pdf", "")
            if pdf and media_exists(pdf):
                actions += (
                    f'<a class="btn btn--ghost btn--sm" href="../../{asset(pdf)}" download>'
                    f'{icon("pdf")} Worksheet</a>'
                )
            rows += f"""<div class="lesson" data-search>
  <span class="lesson__num">{deva_num(f'{i:02d}')}</span>
  <p class="lesson__title">{e(lesson['title'])}</p>
  <div class="lesson__actions">{actions}</div>
</div>"""
        lang_switch = ""
        for other in details:
            if other["key"] == d["key"] and other["lessons"]:
                here = other["lang"] == d["lang"]
                current = ' aria-current="page"' if here else ""
                lang_switch += (
                    f'<a class="chip" href="../{e(other["key"])}-{e(other["lang"])}/"{current} '
                    f'aria-pressed="{"true" if here else "false"}" style="--chip:var(--saffron)">'
                    f'{e(LANG_NATIVE.get(other["lang"], other["lang"]))}</a>'
                )

        body = crumbs(2, [("", "Home"), ("lessons/", "Lessons"), (None, d["title"])]) + f"""
{page_hero('पाठमाला', d['title'], f'{len(d["lessons"])} recorded lessons, in order.', deva=False)}
<div class="toolbar">
  <div class="wrap toolbar__inner">
    <span class="toolbar__label">Language</span>
    <div class="chip-row">{lang_switch}</div>
    <div class="cluster">
      <div class="toolbar__search">{filter_field('lesson-list', 'Filter lessons…', 'lesson-count', with_count=False)}</div>
    </div>
  </div>
</div>
<section class="section" style="padding-top:0">
  <div class="wrap-narrow">
    <div class="syllabus" id="lesson-list">{rows}
      <p class="empty-state" data-empty hidden>No lesson matches that search.</p>
    </div>
    <p class="result-count" id="lesson-count" role="status" aria-live="polite"></p>
  </div>
</section>"""
        page(path=f"lessons/{d['key']}-{d['lang']}/index.html", depth=2, title=d["title"],
             description=f"{d['title']} — {len(d['lessons'])} recorded Sanskrit lessons.",
             body=body, active="lessons/", home=home)


# --------------------------------------------------------------------------- #
# 10. Prahelikās
# --------------------------------------------------------------------------- #
PRAHELIKA_SLUGS = {
    "1": "stotravagahana",
    "2": "samskrta-padalu",
    "3": "jatiyalu",
    "4": "telugu-padalu",
    "5": "patalu-cine-gitalu",
}


def prahelika_slug(s: dict) -> str:
    return PRAHELIKA_SLUGS.get(s["type"], slug(s["title"], "set-" + s["type"]))


def build_prahelikas(data: dict, home: dict) -> None:
    cards = ""
    for i, s in enumerate(data["sets"]):
        n = sum(len(p["questions"]) for p in s["puzzles"])
        cards += (
            f'<a class="card card--link" href="{prahelika_slug(s)}/">'
            f'{cover(s["title"], i + 3, script="telu")}'
            f'<div class="card__body">'
            f'<p class="card__meta">{len(s["puzzles"])} ప్రహేళికలు · {n} ప్రశ్నలు</p></div></a>'
        )

    body = crumbs(1, [("", "Home"), (None, "ప్రహేళికలు")]) + f"""
<section class="section section--tight">
  <div class="wrap">
    <span class="eyebrow">Puzzles</span>
    <h1 class="telu">{e(data['title'])}</h1>
    <p class="hero__lede telu">{e(data['lead'])}</p>
  </div>
</section>
<section class="section" style="padding-top:0">
  <div class="wrap"><div class="grid grid--3">{cards}</div></div>
</section>"""
    page(path="prahelikas/index.html", depth=1, title="ప్రహేళికలు",
         description="Telugu-language Sanskrit puzzles — read the clue, work out the line, then reveal the answer.",
         body=body, active="prahelikas/", home=home)

    for s in data["sets"]:
        puzzles = ""
        for p in s["puzzles"]:
            qa = ""
            for i, q in enumerate(p["questions"]):
                qa += f"""<div class="qa">
  <div class="qa__row">
    <p class="qa__q telu" tabindex="0" role="button" aria-expanded="false">{e(q['q'])}</p>
    <button class="qa__btn" type="button" aria-expanded="false"
            aria-label="సమాధానం చూడండి">సమాధానం చూడండి</button>
  </div>
  <p class="qa__a telu" hidden>{e(q['a'])}</p>
</div>"""
            puzzles += f"""<article class="puzzle" data-search data-total="{len(p['questions'])}">
  <header class="puzzle__head">
    <div class="puzzle__title">
      <h2 class="puzzle__name">{e(p['name'])}</h2>
      {f'<p class="puzzle__author">{e(p["author"])}</p>' if p['author'] else ''}
    </div>
    {f'<p class="puzzle__prompt">{p["prompt"]}</p>' if p['prompt'] else ''}
    <div class="puzzle__bar">
      <button class="btn btn--ghost btn--sm telu" type="button" data-reveal-all aria-pressed="false"
              data-label-show="ఈ ప్రహేళిక అన్ని సమాధానాలు" data-label-hide="సమాధానాలు దాచు">ఈ ప్రహేళిక అన్ని సమాధానాలు</button>
      <span class="puzzle__progress telu" data-progress aria-live="polite">0 / {len(p['questions'])}</span>
    </div>
  </header>
  {qa}
</article>"""

        body = crumbs(2, [("", "Home"), ("prahelikas/", "ప్రహేళికలు"), (None, s["title"])]) + f"""
<section class="section section--tight">
  <div class="wrap">
    <span class="eyebrow">ప్రహేళిక</span>
    <h1 class="telu">{e(s['title'])}</h1>
    {f'<p class="hero__lede telu">{e(s["subtitle"])}</p>' if s['subtitle'] else ''}
  </div>
</section>
<section class="section" style="padding-top:0">
  <div class="wrap">
    <div style="max-width:520px;margin-bottom:1.5rem">{filter_field('puzzle-list', 'ప్రహేళికలలో వెతకండి…', 'puzzle-count')}</div>
    <div id="puzzle-list">{puzzles}
      <p class="empty-state" data-empty hidden>ఏ ప్రహేళిక సరిపోలలేదు.</p>
    </div>
  </div>
</section>"""
        page(path=f"prahelikas/{prahelika_slug(s)}/index.html", depth=2,
             title=s["title"],
             description=f"{s['title']} — {sum(len(p['questions']) for p in s['puzzles'])} Sanskrit puzzle questions in Telugu.",
             body=body, active="prahelikas/", home=home)


# --------------------------------------------------------------------------- #
# 11. Donate
# --------------------------------------------------------------------------- #
def build_donate(data: dict, home: dict) -> None:
    """विद्यादानम् · Gurukula Sevā.

    The school's own words are kept exactly; only their setting changes. The
    numbered instructions were one run-on paragraph of <br>s in the original —
    they are a rite, so they are set as one.
    """
    intro, steps = [], []
    for para in data["paragraphs"]:
        plain = strip_tags(para)
        if re.match(r"^\s*1\s*\.", plain):
            steps = [re.sub(r"^\s*\d+\s*\.\s*", "", line).strip()
                     for line in re.split(r"(?=\b\d\s*\.\s)", plain) if line.strip()]
        else:
            intro.append(para)

    steps_html = ""
    if steps:
        items = "".join(f"<li>{e(x)}</li>" for x in steps)
        steps_html = f"""<div class="panel" style="margin-top:1.5rem">
      <span class="eyebrow">How to give</span>
      <ol class="steps">{items}</ol>
    </div>"""

    plates = "".join(
        f'<figure class="qr-plate">'
        f'<div class="qr-plate__mount">'
        f'<img src="../assets/img/{asset(Path(o["image"]).name)}" alt="{e(o["label"])} payment QR code" loading="lazy">'
        f"</div>"
        f'<figcaption><h3>{e(o["label"])}</h3>'
        f'<p>Scan with the {e(o["label"])} app</p>'
        f'<span class="qr-plate__upi">UPI</span></figcaption></figure>'
        for o in data["options"]
    )

    intro_html = "".join(f"<p>{p}</p>" for p in intro)

    body = crumbs(1, [("", "Home"), (None, "विद्यादानम्")]) + f"""
<section class="section section--tight">
  <div class="wrap">
    <span class="eyebrow deva">विद्यादानम्</span>
    <h1>Gurukula Sevā</h1>
    <p class="hero__lede">{e(data['title'])}. Every reading, gloss and recording on this site was
      prepared by hand at this pāṭhaśālā and given away. If it has been of use to you, you can
      return something towards the work.</p>
  </div>
</section>
<section class="section" style="padding-top:0">
  <div class="wrap-narrow">
    <div class="panel">{intro_html}</div>
    {steps_html}
  </div>
</section>
<section class="section" style="padding-top:0">
  <div class="wrap">
    <div class="section-head section-head--center">
      <span class="eyebrow">Three ways to give</span>
      <h2>Scan and offer</h2>
      <p>Payment goes directly to S Usha Rani through your own UPI app.
         Nothing is collected, stored or processed on this site.</p>
    </div>
    <div class="grid grid--3">{plates}</div>
  </div>
</section>"""
    page(path="donate/index.html", depth=1, title="विद्यादानम् · Gurukula Sevā",
         description="Support the Svarvāṇī Prakāśa Sanskrit pāṭhaśālā — विद्यादानम्.",
         body=body, active="donate/", home=home)


# --------------------------------------------------------------------------- #
# 12. 404 + sitemap + robots
# --------------------------------------------------------------------------- #
def build_extras(home: dict) -> None:
    body = f"""<section class="section" style="text-align:center;padding-block:6rem">
  <div class="wrap-narrow">
    <p class="eyebrow">404</p>
    <h1 class="deva">न विद्यते</h1>
    <p style="font-size:var(--step-1);color:var(--ink-soft)">This page does not exist. It may have moved
      when the site was rebuilt.</p>
    <div class="cluster" style="justify-content:center;margin-top:1.5rem">
      <a class="btn btn--accent" href="/">Home</a>
      <a class="btn btn--ghost" href="/texts/">Texts</a>
      <a class="btn btn--ghost" href="/lessons/">Lessons</a>
    </div>
  </div>
</section>"""
    page(path="404.html", depth=0, title="Not found", description="Page not found.",
         body=body, home=home)

    urls = []
    for path, _ in pages_written:
        if path == "404.html":
            continue
        loc = f"{BASE_URL}/{path[:-len('index.html')] if path.endswith('index.html') else path}"
        urls.append(f"  <url><loc>{e(loc)}</loc></url>")
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(sorted(set(urls))) + "\n</urlset>\n", "utf-8")
    (DIST / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n", "utf-8")
    (DIST / ".nojekyll").write_text("", "utf-8")


# --------------------------------------------------------------------------- #
def copy_assets() -> None:
    target = DIST / "assets"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(ASSETS, target)
    for src, dest in MEDIA_MAP:
        source = MEDIA / src
        if source.exists():
            shutil.copytree(source, DIST / dest, dirs_exist_ok=True)
    for src, dest in MEDIA_FILES:
        source = MEDIA / src
        if source.exists():
            (DIST / dest).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, DIST / dest)


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    copy_assets()

    home = load("home")
    texts = load("texts")
    courses = load("courses")
    course_details = load("course_details")
    stotras = load("stotras")
    stotra_details = load("stotra_details")
    prahelikas = load("prahelikas")
    donate = load("donate")

    build_home(home, texts, courses, stotras, prahelikas)
    build_about(home)
    build_stotras(stotras, stotra_details, home)
    build_texts_index(texts, home)   # populates TEXT_IMAGES for the pages below
    build_verse_corpus("hitopadesha", "hitopadesha", home)
    build_verse_corpus("subhashitas", "subhashitas", home)
    build_adhyayanam(home)
    build_dhatupathah(home)
    build_pre_corpus("raamayan", "raamayana", "अनुक्रमणिका", home, jump=True)
    build_pre_corpus("sulakshana", "sulakshana", "अन्वयः", home, jump=True)
    build_pre_corpus("saritsaagara", "saritsagara", "अन्वयः", home, jump=True)
    build_gita(home)
    build_vishnu(home)
    build_lessons(courses, course_details, home)
    build_prahelikas(prahelikas, home)
    build_donate(donate, home)
    build_extras(home)

    total = sum(kb for _, kb in pages_written)
    print(f"Built {len(pages_written)} pages into dist/  ({total/1024:.1f} MB of HTML)")
    for path, kb in sorted(pages_written, key=lambda x: -x[1])[:10]:
        print(f"  {kb:8.1f} KB  {path}")


if __name__ == "__main__":
    main()
