#!/usr/bin/env python3
"""Extract the content of the original samskrtam.info mirror into structured JSON.

The original site is a hand-written PHP/Bootstrap template where the scholarly
content (verses, word-splits, glosses, lesson lists, puzzles) is inlined into the
markup.  This script lifts that content out verbatim so the modern site can
render it from data instead of from a frozen HTML soup.  Nothing is rewritten or
translated here - only structure is recovered.
"""
from __future__ import annotations

import html
import json
import os
import re
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "original-site"
OUT = ROOT / "src" / "data"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def soup_of(name: str) -> BeautifulSoup:
    raw = (SRC / name).read_text("utf-8", errors="replace")
    # The stotra and donate pages break their lines with `</br>` — a stray end
    # tag. Browsers render it as a line break; a parser drops it on the floor,
    # taking every line break in the stotra texts with it. Normalise first.
    raw = re.sub(r"</\s*br\s*>", "<br>", raw, flags=re.I)
    return BeautifulSoup(raw, "lxml")


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = text.replace(" ", " ")
    return re.sub(r"[ \t]*\n[ \t]*", "\n", re.sub(r"[ \t]+", " ", text)).strip()


def inline_html(node: Tag) -> str:
    """Serialise a node's children, keeping only <br>, <a>, <b>/<strong>, <i>/<em>."""
    keep = {"br", "a", "b", "strong", "i", "em", "sup", "sub"}
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            parts.append(html.escape(str(child)))
        elif isinstance(child, Tag):
            if child.name == "br":
                parts.append("<br>")
            elif child.name == "a" and child.get("href"):
                href = child["href"]
                parts.append(f'<a href="{html.escape(href)}">{clean(child.get_text())}</a>')
            elif child.name in keep:
                parts.append(f"<{child.name}>{inline_html(child)}</{child.name}>")
            else:
                parts.append(inline_html(child))
    out = "".join(parts)
    out = re.sub(r"(?:<br>\s*){3,}", "<br><br>", out)
    out = re.sub(r"[ \t]+", " ", out)
    return out.strip()


def blocks_from_br(node: Tag) -> list[str]:
    """Split a <br>-separated blob into paragraphs."""
    raw = inline_html(node)
    chunks = re.split(r"(?:<br>\s*){2,}", raw)
    return [c.strip() for c in (x.replace("<br>", "\n") for x in chunks) if c.strip()]


def youtube_id(url: str) -> str:
    m = re.search(r"(?:embed/|v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else ""


def slugify(text: str, fallback: str = "item") -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text or fallback


def dump(name: str, payload) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    size = path.stat().st_size
    n = len(payload) if isinstance(payload, list) else len(payload.get("items", payload))
    print(f"  {name:24s} {size/1024:8.1f} KB  ({n} top-level entries)")


# --------------------------------------------------------------------------- #
# home
# --------------------------------------------------------------------------- #
def extract_home() -> dict:
    s = soup_of("home.php")
    welcome = {}
    for lang in ("sanskrit", "telugu", "english"):
        p = s.select_one(f"p.{lang}")
        if p:
            welcome[lang] = clean(p.get_text())

    videos = []
    for wrap in s.select(".notice-right-wrapper, .notice-left-wrapper"):
        head = wrap.find(["h3"])
        frame = wrap.find("iframe")
        if frame:
            videos.append({
                "title": clean(head.get_text()) if head else "",
                "youtube": youtube_id(frame.get("src", "")),
            })

    tiles = []
    for card in s.select(".course-area .single-course"):
        a, img = card.find("a"), card.find("img")
        if not img:
            continue
        tiles.append({
            "image": clean(img.get("src", "")),
            "href": clean(a.get("href", "")) if a else "",
            "label": Path(clean(img.get("src", ""))).stem,
        })

    footer = s.select_one("footer")
    social = []
    for a in footer.select(".footer-social a"):
        icon = a.find("i")
        cls = " ".join(icon.get("class", [])) if icon else ""
        name = re.sub(r".*zmdi-([a-z]+).*", r"\1", cls) or "link"
        social.append({"name": name, "href": a.get("href", "")})

    contact = footer.select_one(".single-widget:last-of-type")
    return {
        "title": clean(s.title.get_text()) if s.title else "Samskrtam",
        "meta_description": (s.find("meta", attrs={"name": "description"}) or {}).get("content", ""),
        "welcome": welcome,
        "videos": videos,
        "tiles": tiles,
        "social": social,
        "contact": clean(contact.get_text()) if contact else "",
    }


# --------------------------------------------------------------------------- #
# stotras
# --------------------------------------------------------------------------- #
SCRIPT_OF_CLASS = {"b1": "devanagari", "b2": "telugu", "b3": "iast"}


def extract_stotras() -> list[dict]:
    s = soup_of("stotras.php")
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for col in s.select(".row > div[class*=customFilter]"):
        classes = col.get("class", [])
        script = next((SCRIPT_OF_CLASS[c] for c in classes if c in SCRIPT_OF_CLASS), "devanagari")
        keywords = [c for c in classes
                    if c not in SCRIPT_OF_CLASS and not c.startswith(("col-", "customFilter"))]
        a = col.find("a", class_="courseBlueButton")
        frame = col.find("iframe")
        if not a:
            continue
        label = clean(a.get_text())
        # card titles read "<Name>- Devanagari" / "- Devanagari Telugu" / "- Devanagari IAST"
        name = re.sub(r"\s*-\s*Devanagari(\s+(Telugu|IAST))?\s*$", "", label).strip()
        key = "-".join(keywords) or slugify(name)
        if key not in grouped:
            order.append(key)
            grouped[key] = {
                "slug": slugify(name),
                "title": name,
                "keywords": keywords,
                "detail": clean(a.get("href", "")),
                "versions": [],
            }
        grouped[key]["versions"].append({
            "script": script,
            "label": label,
            "youtube": youtube_id(frame.get("src", "")) if frame else "",
        })
    return [grouped[k] for k in order]


def extract_stotra_details() -> list[dict]:
    details = []
    for path in sorted(SRC.glob("stotra.php?id=*")):
        sid = path.name.split("=")[-1]
        s = soup_of(path.name)
        title = clean(s.select_one(".section-title h2").get_text())
        sections = []
        labels = {}
        for btn in s.select("button.lang-btn"):
            labels[btn.get("id", "")] = clean(btn.get_text())

        intro = s.select_one("#section4")
        frame = s.select_one(".embed-responsive iframe")
        for div_id, cls in (("section1", "b1"), ("section2", "b2"), ("section3", "b3")):
            node = s.select_one(f"#{div_id}")
            if not node:
                continue
            body = inline_html(node)
            heading = ""
            m = re.match(r"([^<]{0,60}?):<br>", body)
            if m:
                heading, body = m.group(1).strip(), body[m.end():]
            sections.append({
                "id": div_id,
                "script_class": cls,
                "tab": labels.get(cls, heading or div_id),
                "heading": heading,
                "body": body.strip(),
            })
        details.append({
            "id": sid,
            "slug": slugify(title),
            "title": title,
            "intro": inline_html(intro) if intro else "",
            "youtube": youtube_id(frame.get("src", "")) if frame else "",
            "sections": sections,
        })
    return details


# --------------------------------------------------------------------------- #
# texts index
# --------------------------------------------------------------------------- #
def extract_texts() -> list[dict]:
    s = soup_of("texts.php")
    groups = []
    for block in s.select(".single-event .event-content"):
        head = block.find("h4")
        items = []
        for a in block.select("a.btn-link"):
            img = a.find("img")
            items.append({
                "href": clean(a.get("href", "")),
                "title": clean(a.get_text()),
                "image": clean(img.get("src", "")) if img else "",
            })
        if items:
            groups.append({"title": clean(head.get_text()) if head else "", "items": items})
    return groups


# --------------------------------------------------------------------------- #
# courses
# --------------------------------------------------------------------------- #
LANG_LABEL = {"hindi": "हिन्दी", "telugu": "తెలుగు", "english": "ENGLISH"}


def extract_courses() -> list[dict]:
    s = soup_of("courses.php")
    courses = []
    for card in s.select("div[class*=customFilter]"):
        img = card.find("img")
        name_el = card.select_one(".default-btn")
        if not name_el:
            continue
        langs = []
        key = ""
        for a in card.select("a.lang-btn"):
            href = a.get("href", "")
            q = dict(re.findall(r"(\w+)=([^&]+)", href))
            langs.append({"lang": q.get("lang", ""), "label": clean(a.get_text()), "href": href})
            key = q.get("name", key)
        courses.append({
            "key": key,
            "title": clean(name_el.get_text()),
            "image": clean(img.get("src", "")) if img else "",
            "keywords": [c for c in card.get("class", [])
                         if not c.startswith(("col-", "customFilter"))],
            "languages": langs,
        })
    return courses


def extract_course_details() -> list[dict]:
    out = []
    for path in sorted(SRC.glob("course.php?lang=*")):
        q = dict(re.findall(r"(\w+)=([^&]+)", path.name.split("?", 1)[1]))
        s = soup_of(path.name)
        head = s.select_one(".section-title h2")
        lessons = []
        for card in s.select(".single-course"):
            title_el = card.select_one(".courseBlueButton")
            frame = card.find("iframe")
            pdf = card.find("a", href=re.compile(r"\.pdf$", re.I))
            if not title_el:
                continue
            lessons.append({
                "title": clean(title_el.get_text()),
                "youtube": youtube_id(frame.get("src", "")) if frame else "",
                "pdf": clean(pdf.get("href", "")) if pdf else "",
            })
        out.append({
            "key": q.get("name", ""),
            "lang": q.get("lang", ""),
            "title": clean(head.get_text()) if head else "",
            "lessons": lessons,
        })
    return out


# --------------------------------------------------------------------------- #
# prahelikas (Telugu puzzles)
# --------------------------------------------------------------------------- #
def extract_prahelikas() -> dict:
    s = soup_of("prahelikas.php")
    head = s.select_one(".section-title h2")
    lead = s.select_one(".course-content h2")
    cats = []
    for a in s.select("a.btn-link"):
        href = a.get("href", "")
        m = re.search(r"type=(\d+)", href)
        cats.append({"type": m.group(1) if m else "", "title": clean(a.get_text())})

    sets = []
    for path in sorted(SRC.glob("prahelika.php?type=*")):
        t = path.name.split("=")[-1]
        p = soup_of(path.name)
        ptitle = clean(p.select_one(".section-title h2").get_text())
        subtitle_el = p.select_one(".section-title h3")
        puzzles = []
        for block in p.select(".puzzle-block"):
            name_el = block.select_one("h2.telugu")
            author_el = block.select_one(".course-content div[style*='0.85em']")
            prompt_el = block.select_one("h2.b6") or block.select_one("h2[style*='1.2em']")
            questions = []
            for wrap in block.select(".question-wrapper"):
                q = wrap.select_one("div.original.b1")
                a = wrap.select_one("div.answer-text")
                if q is None:
                    continue
                questions.append({"q": clean(q.get_text()), "a": clean(a.get_text()) if a else ""})
            if questions:
                puzzles.append({
                    "name": clean(name_el.get_text()) if name_el else "",
                    "author": clean(author_el.get_text()) if author_el else "",
                    "prompt": inline_html(prompt_el) if prompt_el else "",
                    "questions": questions,
                })
        sets.append({
            "type": t,
            "title": ptitle,
            "subtitle": clean(subtitle_el.get_text()) if subtitle_el else "",
            "puzzles": puzzles,
        })
    return {
        "title": clean(head.get_text()) if head else "",
        "lead": clean(lead.get_text()) if lead else "",
        "categories": cats,
        "sets": sets,
    }


# --------------------------------------------------------------------------- #
# donate
# --------------------------------------------------------------------------- #
def extract_donate() -> dict:
    s = soup_of("donate.php")
    content = s.select_one(".subscribe-content")
    paras = [inline_html(p) for p in content.find_all("p")] if content else []
    options = []
    for card in s.select(".single-event"):
        img, head = card.find("img"), card.find("h4")
        if img:
            options.append({
                "label": clean(head.get_text()) if head else "",
                "image": clean(img.get("src", "")),
            })
    head = content.find("h2") if content else None
    return {
        "title": clean(head.get_text()) if head else "Namaste",
        "paragraphs": [p for p in paras if p],
        "options": options,
    }


# --------------------------------------------------------------------------- #
# verse-table corpora (hitopadesha, subhashitas)
# --------------------------------------------------------------------------- #
def extract_verse_corpus(page: str) -> dict:
    s = soup_of(page)
    head = s.select_one(".section-title h2")
    intro_parts = []
    lead = s.select_one(".course-content span.sanskrit")
    if lead:
        intro_parts.extend(blocks_from_br(lead))
    more = s.select_one("#intromore")
    if more:
        intro_parts.extend(blocks_from_br(more))

    toggles = []
    for btn in s.select("div.course-content button.lang-btn"):
        bid = btn.get("id", "")
        if bid and bid not in {"more1", "less1"}:
            toggles.append({"key": bid, "label": clean(btn.get_text())})

    verses = []
    for node in s.select("div.total"):
        vid = node.get("id", "")
        fields = {}
        audio = ""
        for tr in node.select("tr"):
            cls = " ".join(tr.get("class", []))
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            key = cls.strip().split()[0] if cls.strip() else ""
            src = tr.find("source")
            if src:
                audio = clean(src.get("src", ""))
                continue
            fields[key] = {"label": clean(tds[0].get_text()).rstrip(":").strip(),
                           "value": inline_html(tds[1])}
        if fields or audio:
            verses.append({"id": vid, "fields": fields, "audio": audio})
    return {
        "title": clean(head.get_text()) if head else "",
        "intro": intro_parts,
        "toggles": toggles,
        "verses": verses,
    }


# --------------------------------------------------------------------------- #
# adhyayanam XML corpus
# --------------------------------------------------------------------------- #
def extract_adhyayanam() -> dict:
    from xml.etree import ElementTree as ET

    raw = (SRC / "xml" / "adhyayanam.xml").read_text("utf-8", errors="replace")
    root = ET.fromstring(raw)
    sections = []
    for sec in root.findall("section"):
        groups = []
        for g in sec.findall("group"):
            entry = {"ident": g.get("ident", ""), "type": g.get("type", "")}
            for tag, key in (("F", "moolam"), ("A", "pada"), ("P", "tippani"),
                             ("C", "vishleshanam"), ("E", "english")):
                el = g.find(tag)
                if el is not None and (el.text or "").strip():
                    lines = [ln.strip() for ln in el.text.strip().splitlines() if ln.strip()]
                    entry[key] = lines
            groups.append(entry)
        sections.append({
            "n": sec.get("n", ""),
            "title": sec.get("title", ""),
            "groups": groups,
        })
    return {"title": "हितोपदेश-अध्ययनम्", "sections": sections}


# --------------------------------------------------------------------------- #
# dhatupathah table
# --------------------------------------------------------------------------- #
def extract_dhatupathah() -> dict:
    s = soup_of("dhatupathah.php")
    head = s.select_one(".section-title h2")
    note = s.select_one(".course-content span")
    table = s.find("table")
    header = [clean(td.get_text()) for td in table.select("thead td")]
    header = [h for h in header if h]
    # `td:last-child { display:none }` in the original stylesheet hides a ninth
    # column that 704 rows actually fill in (इदित्, उदित्, citations). It is the
    # school's own data, so the modern table shows it as टिप्पणी.
    header = header + ["टिप्पणी"]
    rows = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        cells = [clean(td.get_text()) for td in tds]
        tail = cells[8] if len(cells) > 8 else ""          # the hidden ninth column
        cells = cells[:8] + [""] * max(0, 8 - len(cells))
        row = cells[:8] + [tail]
        if any(row):
            rows.append(row)
    return {
        "title": clean(head.get_text()) if head else "",
        "note": blocks_from_br(note) if note else [],
        "columns": header,
        "rows": rows,
    }


# --------------------------------------------------------------------------- #
# <pre>-section corpora (raamayan, sulakshana, saritsaagara)
# --------------------------------------------------------------------------- #
RAAMAYAN_LABELS = {
    "topSection": "उपोद्घातः",
    "firstSection": "बालकाण्डे",
    "secondSection": "अयोध्याकाण्डे",
    "thirdSection": "अरण्यकाण्डे",
    "fourthSection": "किष्किन्धाकाण्डे",
    "fifthSection": "सुन्दरकाण्डे",
    "sixthSection": "युद्धकाण्डे",
    "seventhSection": "उत्तरकाण्डे",
    "eighthSection": "प्रक्षिप्तसर्गे",
}


PRE_VERSE_LABELS = {
    "moolam": "मूलम्",
    "pada": "पदविभागः",
    "anvaya": "अन्वयः",
    "prati": "तात्पर्यम्",
    "taatparyam": "तात्पर्यम्",
}


def extract_pre_corpus(page: str, labels: dict[str, str] | None = None) -> dict:
    s = soup_of(page)
    head = s.select_one(".section-title h2")
    intro = s.select_one(".course-content span.sanskrit") or s.select_one(".course-content h2")
    sections = []
    for node in s.select("div[id$=Section]"):
        sid = node.get("id", "")
        title_el = node.find(["h2", "h3"])
        parts = []
        for pre in node.find_all("pre"):
            text = pre.get_text()
            text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
            if text.strip():
                parts.append(text)

        # some sections hold div.total verse blocks instead of <pre> runs
        verses = []
        for block in node.select("div.total"):
            fields = {}
            for key, label in PRE_VERSE_LABELS.items():
                cell = block.select_one(f"div.{key}")
                if cell is None:
                    continue
                value = clean(cell.get_text())
                value = re.sub(r"^[^-]{0,18}-\s*", "", value, count=1)
                if value:
                    fields[key] = {"label": label, "value": html.escape(value)}
            if fields:
                verses.append({"id": str(len(verses) + 1), "fields": fields, "audio": ""})

        if parts or verses:
            sections.append({
                "id": sid,
                "title": (labels or {}).get(sid) or (clean(title_el.get_text()) if title_el else ""),
                "parts": parts,
                "verses": verses,
            })
    return {
        "title": clean(head.get_text()) if head else "",
        "intro": blocks_from_br(intro) if intro else [],
        "sections": sections,
    }


# --------------------------------------------------------------------------- #
# gita (speaker-tagged running prose) and vishnu
# --------------------------------------------------------------------------- #
SPEAKERS = {
    "krishna": "श्रीभगवानुवाच",
    "arjuna": "अर्जुन",
    "sanjaya": "सञ्जय",
    "dritarashtra": "धृतराष्ट्र",
}


def extract_gita() -> dict:
    s = soup_of("gita.php")
    head = s.select_one(".section-title h2")
    intro = s.select_one(".course-content span.sanskrit")
    chapters = []
    current = None
    pending: list[dict] = []   # blocks that precede the first chapter heading
    body = s.select_one(".subscribe-area .container")
    for node in body.find_all(["div"], recursive=True):
        classes = node.get("class", [])
        if "section-title" in classes and node.get("id", "").startswith("ch"):
            h = node.find("h2")
            current = {"id": node.get("id"), "title": clean(h.get_text()) if h else "", "blocks": []}
            if pending:
                # Gītā 1.1 (धृतराष्ट्र उवाच) is marked up before the chapter-1
                # heading in the original; it belongs to chapter 1.
                current["blocks"].extend(pending)
                pending = []
            chapters.append(current)
        elif "gita" in classes and current is None:
            speaker = next((c for c in classes if c in SPEAKERS), "")
            p = node.find(["p", "pre"])
            img = node.find("img")
            if p and clean(p.get_text()):
                pending.append({
                    "speaker": speaker,
                    "speaker_label": SPEAKERS.get(speaker, ""),
                    "avatar": clean(img.get("src", "")).lstrip("/") if img else "",
                    "text": clean(p.get_text()),
                })
        elif "gita" in classes and current is not None:
            speaker = next((c for c in classes if c in SPEAKERS), "")
            p = node.find(["p", "pre"])
            img = node.find("img")
            if p and clean(p.get_text()):
                current["blocks"].append({
                    "speaker": speaker,
                    "speaker_label": SPEAKERS.get(speaker, ""),
                    "avatar": clean(img.get("src", "")).lstrip("/") if img else "",
                    "text": clean(p.get_text()),
                })
    return {
        "title": clean(head.get_text()) if head else "",
        "intro": blocks_from_br(intro) if intro else [],
        "speakers": [{"key": k, "label": v} for k, v in SPEAKERS.items()],
        "chapters": [c for c in chapters if c["blocks"]],
    }


def extract_vishnu() -> dict:
    s = soup_of("vishnu.php")
    head = s.select_one(".section-title h2")
    intro = s.select_one(".course-content h2")
    blocks = []
    for node in s.select("div.gita"):
        classes = node.get("class", [])
        speaker = next((c for c in classes if c in SPEAKERS), "")
        pre = node.find("pre")
        img = node.find("img")
        if pre and clean(pre.get_text()):
            blocks.append({
                "speaker": speaker,
                "avatar": clean(img.get("src", "")).lstrip("/") if img else "",
                "text": re.sub(r"\n{3,}", "\n\n", pre.get_text()).strip(),
            })
    sections = []
    for node in s.select("div[id$=Section]"):
        title_el = node.find(["h2"])
        parts = [re.sub(r"\n{3,}", "\n\n", pre.get_text()).strip()
                 for pre in node.find_all("pre") if pre.get_text().strip()]
        if parts:
            sections.append({
                "id": node.get("id", ""),
                "title": clean(title_el.get_text()) if title_el else "",
                "parts": parts,
            })
    return {
        "title": clean(head.get_text()) if head else "",
        "intro": blocks_from_br(intro) if intro else [],
        "blocks": blocks,
        "sections": sections,
    }


# --------------------------------------------------------------------------- #
def main() -> None:
    print("Extracting content from original-site/ ...")
    dump("home", extract_home())
    dump("stotras", extract_stotras())
    dump("stotra_details", extract_stotra_details())
    dump("texts", extract_texts())
    dump("courses", extract_courses())
    dump("course_details", extract_course_details())
    dump("prahelikas", extract_prahelikas())
    dump("donate", extract_donate())
    dump("hitopadesha", extract_verse_corpus("hitopadesha.php"))
    dump("subhashitas", extract_verse_corpus("subhashitas.php"))
    dump("adhyayanam", extract_adhyayanam())
    dump("dhatupathah", extract_dhatupathah())
    dump("raamayan", extract_pre_corpus("raamayan.php", RAAMAYAN_LABELS))
    dump("sulakshana", extract_pre_corpus("sulakshana.php"))
    dump("saritsaagara", extract_pre_corpus("saritsaagara.php"))
    dump("gita", extract_gita())
    dump("vishnu", extract_vishnu())
    print("done.")


if __name__ == "__main__":
    main()
