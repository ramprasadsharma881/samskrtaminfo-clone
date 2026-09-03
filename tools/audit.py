#!/usr/bin/env python3
"""Parity audit: does dist/ still carry everything original-site/ has?

Run after every build. It compares the generated site against the mirror rather
than against expectations, so a regression in extraction or rendering shows up
as a number, not as something noticed by eye three weeks later.

    python3 tools/audit.py
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urljoin

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
ORIG = ROOT / "original-site"
DIST = ROOT / "dist"

DEVA = re.compile(r"[ऀ-ॿ]")
TELU = re.compile(r"[ఀ-౿]")

# every page of the original, and where it lives now
PAGES = {
    "home.php": "index.html",
    "stotras.php": "stotras/index.html",
    "stotra.php?id=1": "stotras/narasimha-pada-stotra/index.html",
    "stotra.php?id=2": "stotras/totakashtakam/index.html",
    "texts.php": "texts/index.html",
    "hitopadesha.php": "texts/hitopadesha/index.html",
    "subhashitas.php": "texts/subhashitas/index.html",
    "hitopadesha-adhyayana.php": "texts/adhyayanam/index.html",
    "dhatupathah.php": "texts/dhatupathah/index.html",
    "raamayan.php": "texts/raamayana/index.html",
    "gita.php": "texts/gita/index.html",
    "sulakshana.php": "texts/sulakshana/index.html",
    "saritsaagara.php": "texts/saritsagara/index.html",
    "vishnu.php": "texts/vishnusahasranama/index.html",
    "courses.php": "lessons/index.html",
    "prahelikas.php": "prahelikas/index.html",
    "prahelika.php?type=1": "prahelikas/stotravagahana/index.html",
    "prahelika.php?type=2": "prahelikas/samskrta-padalu/index.html",
    "prahelika.php?type=3": "prahelikas/jatiyalu/index.html",
    "prahelika.php?type=4": "prahelikas/telugu-padalu/index.html",
    "prahelika.php?type=5": "prahelikas/patalu-cine-gitalu/index.html",
    "donate.php": "donate/index.html",
}

# the original's whole menu, including the entries that never went anywhere
MENU = ["Home", "Contact", "About", "Donate", "Useful Links", "Stotras", "Songs",
        "Text Contents", "Lessons", "Articles", "ప్రహేళికలు", "Worker Links", "Blogs"]

failures: list[str] = []
notes: list[str] = []


def soup(path: Path) -> BeautifulSoup:
    raw = path.read_text("utf-8", errors="replace")
    raw = re.sub(r"</\s*br\s*>", "<br>", raw, flags=re.I)
    return BeautifulSoup(raw, "lxml")


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{('  — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def videos(s: BeautifulSoup) -> set[str]:
    out = set()
    for f in s.find_all("iframe"):
        m = re.search(r"embed/([A-Za-z0-9_-]{6,})", f.get("src", "") or "")
        if m:
            out.add(m.group(1))
    for el in s.select("[data-yt]"):
        out.add(el["data-yt"])
    for a in s.select('a[href*="youtube.com/watch"]'):
        m = re.search(r"v=([A-Za-z0-9_-]{6,})", a["href"])
        if m:
            out.add(m.group(1))
    return out


def outbound(s: BeautifulSoup) -> set[str]:
    return {
        a["href"].rstrip("/")
        for a in s.find_all("a", href=True)
        if a["href"].startswith(("http://", "https://"))
        and not any(x in a["href"] for x in ("samskrtam.info", "youtube", "ytimg"))
    }


def main() -> int:
    if not DIST.exists():
        sys.exit("dist/ not found — run tools/build.py first")

    print("\n1 · Every original page has a home")
    missing_pages = [src for src, dst in PAGES.items() if not (DIST / dst).exists()]
    check(f"{len(PAGES)} mapped pages exist", not missing_pages, ", ".join(missing_pages))
    for f in ORIG.glob("course.php?lang=*"):
        q = dict(re.findall(r"(\w+)=([^&]+)", f.name.split("?", 1)[1]))
        PAGES[f.name] = f"lessons/{q['name']}-{q['lang']}/index.html"
    missing_courses = [s for s, d in PAGES.items()
                       if s.startswith("course.php") and not (DIST / d).exists()]
    check("25 course pages exist", not missing_courses, ", ".join(missing_courses))

    print("\n2 · Nothing embedded or cited was dropped")
    orig_v, dist_v, orig_l, dist_l = set(), set(), set(), set()
    for f in ORIG.glob("*.php*"):
        s = soup(f)
        orig_v |= videos(s)
        orig_l |= outbound(s)
    for f in DIST.rglob("*.html"):
        s = soup(f)
        dist_v |= videos(s)
        dist_l |= outbound(s)
    check(f"{len(orig_v)} embedded videos", not (orig_v - dist_v),
          f"missing {sorted(orig_v - dist_v)[:5]}")
    check(f"{len(orig_l)} outbound citations", not (orig_l - dist_l),
          f"missing {sorted(orig_l - dist_l)[:5]}")

    print("\n3 · The scholarship itself, character for character")
    # Compare the scholarly cells directly. Whole-page text would also count
    # the original's chrome — it repeats all seven register labels as buttons
    # on every one of 227 verses — which says nothing about the content.
    for label, dst, dsel, src, osel in [
        ("Hitopadeśa registers", "texts/hitopadesha/index.html", ".layer__value",
         "hitopadesha.php", "div.total table tr td:nth-child(2)"),
        ("Subhāṣita registers", "texts/subhashitas/index.html", ".layer__value",
         "subhashitas.php", "div.total table tr td:nth-child(2)"),
        ("dhātu cells", "texts/dhatupathah/index.html", "tbody td",
         "dhatupathah.php", "tbody td"),
    ]:
        a = len(DEVA.findall(" ".join(x.get_text(" ") for x in soup(DIST / dst).select(dsel))))
        b = len(DEVA.findall(" ".join(x.get_text(" ") for x in soup(ORIG / src).select(osel))))
        check(f"{label:22s} {a} Devanagari characters", a == b, f"original has {b}")

    print("\n3b · Whole-page coverage (chrome differences allowed)")
    for src, dst in [("hitopadesha.php", "texts/hitopadesha/index.html"),
                     ("subhashitas.php", "texts/subhashitas/index.html"),
                     ("dhatupathah.php", "texts/dhatupathah/index.html"),
                     ("gita.php", "texts/gita/index.html"),
                     ("raamayan.php", "texts/raamayana/index.html"),
                     ("sulakshana.php", "texts/sulakshana/index.html"),
                     ("saritsaagara.php", "texts/saritsagara/index.html"),
                     ("vishnu.php", "texts/vishnusahasranama/index.html"),
                     ("stotra.php?id=1", "stotras/narasimha-pada-stotra/index.html"),
                     ("stotra.php?id=2", "stotras/totakashtakam/index.html")]:
        a = len(DEVA.findall(soup(DIST / dst).get_text(" ")))
        b = len(DEVA.findall(soup(ORIG / src).get_text(" ")))
        pct = a / b * 100 if b else 100
        # the original repeats every register label as a button on every verse;
        # 92% is the floor once that chrome is not duplicated hundreds of times
        check(f"{src:24s} Devanagari {pct:6.1f}% of original", pct >= 92,
              f"{a} vs {b}")
    for src, dst in [("prahelika.php?type=1", "prahelikas/stotravagahana/index.html"),
                     ("prahelika.php?type=2", "prahelikas/samskrta-padalu/index.html"),
                     ("prahelika.php?type=3", "prahelikas/jatiyalu/index.html"),
                     ("prahelika.php?type=4", "prahelikas/telugu-padalu/index.html"),
                     ("prahelika.php?type=5", "prahelikas/patalu-cine-gitalu/index.html")]:
        a = len(TELU.findall(soup(DIST / dst).get_text(" ")))
        b = len(TELU.findall(soup(ORIG / src).get_text(" ")))
        pct = a / b * 100 if b else 100
        check(f"{src:24s} Telugu     {pct:6.1f}% of original", pct >= 95, f"{a} vs {b}")

    print("\n4 · Counts match the mirror")
    def n(dst: str, sel: str) -> int:
        return len(soup(DIST / dst).select(sel))
    for label, got, want in [
        ("Hitopadeśa verses", n("texts/hitopadesha/index.html", ".verse"), 227),
        ("Subhāṣita verses", n("texts/subhashitas/index.html", ".verse"), 136),
        ("dhātu rows", n("texts/dhatupathah/index.html", "tbody tr"), 2101),
        ("Gītā passages", n("texts/gita/index.html", ".speech"), 59),
        ("adhyayanam entries",
         sum(len(soup(f).select(".verse")) for f in DIST.glob("texts/adhyayanam/*/**/index.html")), 1557),
        ("lessons", sum(len(soup(f).select(".lesson")) for f in DIST.glob("lessons/*/index.html")), 530),
        ("prahelikā questions",
         sum(len(soup(f).select(".qa")) for f in DIST.glob("prahelikas/*/index.html")), 446),
        ("stotra recordings", n("stotras/index.html", "[data-script]"), 6),
    ]:
        check(f"{label}: {got}", got == want, f"expected {want}")

    print("\n5 · Every menu entry the school published is represented")
    text = " ".join(soup(f).get_text(" ") for f in DIST.rglob("*.html")).lower()
    absent = [m for m in MENU if m.lower() not in text]
    check(f"all {len(MENU)} original menu labels appear somewhere", not absent,
          ", ".join(absent))

    print("\n6 · Assets ship and are referenced")
    used = set()
    for f in DIST.rglob("*.html"):
        for m in re.findall(r'(?:src|href)="([^"]+)"', f.read_text("utf-8")):
            if "assets/" in m:
                used.add(Path(m).name)
                used.add(unquote(Path(m).name))
    for kind, folder in [("images", DIST / "assets/img"),
                         ("audio", DIST / "assets/audio/hitopadesa"),
                         ("fonts", DIST / "assets/fonts")]:
        have = {p.name for p in folder.glob("*")} if folder.exists() else set()
        orphan = sorted(have - used)
        if kind == "fonts":
            check(f"{kind}: {len(have)} shipped", len(have) == 3)
            continue
        if kind == "images":
            orphan = [o for o in orphan if o != "loading.gif"]
            if "loading.gif" in have:
                notes.append("loading.gif is unused — the original needed a spinner "
                             "while it fetched adhyayanam.xml; these pages are pre-rendered")
        check(f"{kind}: {len(have)} shipped, {len(have & used)} referenced", not orphan,
              f"orphans {orphan[:6]}")

    print("\n7 · Internal integrity")
    broken = 0
    checked = 0
    dupes = []
    for f in sorted(DIST.rglob("*.html")):
        rel = "/" + str(f.relative_to(DIST))
        s = soup(f)
        ids = [x.get("id") for x in s.find_all(id=True)]
        d = [k for k, v in collections.Counter(ids).items() if v > 1]
        if d:
            dupes.append((rel, d))
        for tag, attr in (("a", "href"), ("img", "src"), ("script", "src"),
                          ("link", "href"), ("audio", "src"), ("source", "src")):
            for el in s.find_all(tag):
                v = el.get(attr)
                if not v or v.startswith(("#", "mailto:", "data:", "javascript:", "http", "//")):
                    continue
                checked += 1
                t = urljoin(rel, v).split("#")[0].split("?")[0]
                p = DIST / unquote(t.lstrip("/"))
                if t.endswith("/"):
                    p = DIST / unquote(t.strip("/")) / "index.html"
                elif p.is_dir():
                    p = p / "index.html"
                if not p.exists():
                    broken += 1
                    print("        BROKEN", rel, v)
    check(f"{checked} internal references resolve", broken == 0, f"{broken} broken")
    check("no duplicate element ids", not dupes, str(dupes[:3]))

    print()
    for note in notes:
        print(f"  note  {note}")
    print(f"\n{'ALL CHECKS PASS' if not failures else str(len(failures)) + ' CHECK(S) FAILED'}")
    for f in failures:
        print("   -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
