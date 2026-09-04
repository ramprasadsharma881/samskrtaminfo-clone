#!/usr/bin/env python3
"""Cut a favicon from the school's own identity.

The site shipped a stock green-and-pink "Ht" mark left over from the template
it was built on — the one identity surface on the whole site that is not
theirs. Their own seal, the haṃsa over the open book, is drawn as a hairline
with a ring of Devanagari around it: at 16px it dissolves into grey no matter
how the strokes are weighted (both were tried).

So the tab mark is सं instead — the first syllable of संस्कृतम्, which is what
the whole site is, and the first word of the motto struck on their seal:
संस्कृतं स्वधर्मस्य मूलम्. Set in Sanskrit2003, the typeface the school already
licensed and the site already serves, in the site's own ink on its own
parchment. It is legible at 16px, unmistakably theirs, and nothing was
invented to make it.

Run once; the result is committed at src/assets/img/favicon.png and the build
copies it with the rest of src/assets/. Needs Pillow, which the build itself
does not — this is a one-off tool, not a build step.

    python3 tools/make_favicon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "original-site" / "fonts" / "Sanskrit2003.ttf"
OUT = ROOT / "src" / "assets" / "img" / "favicon.png"

GLYPH = "सं"
PARCHMENT = (250, 246, 238)   # --paper
INK = (28, 25, 23)            # --ink-primary
SIZE = 256


def main() -> None:
    # rendered large and reduced, so the curves stay smooth at every tab size
    canvas = SIZE * 4
    img = Image.new("RGB", (canvas, canvas), PARCHMENT)
    draw = ImageDraw.Draw(img)

    # fit the glyph to ~78% of the square, leaving the margin a mark needs
    font = ImageFont.truetype(str(FONT), int(canvas * 0.74))
    box = draw.textbbox((0, 0), GLYPH, font=font)
    draw.text(((canvas - (box[2] - box[0])) / 2 - box[0],
               (canvas - (box[3] - box[1])) / 2 - box[1]),
              GLYPH, font=font, fill=INK)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.resize((SIZE, SIZE), Image.LANCZOS).save(OUT, optimize=True)
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
