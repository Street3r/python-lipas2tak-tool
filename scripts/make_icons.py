"""Draw the outdoor icon set (icons/retkeily/*.png).

Original pictograms in the general style of outdoor recreation maps:
a coloured rounded square with a white symbol. These are this project's own
drawings, not Metsähallitus symbols.

Run: python scripts/make_icons.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "icons" / "retkeily"
S = 256          # drawing size (downscaled to 64 px for antialiasing)
OUT_SIZE = 64
W = "white"
LW = 16          # line width at drawing size

# Group colours (same as the groups in types.yaml)
BROWN = "#7A4A24"    # shelters
ORANGE = "#C8551B"   # fire places
SLATE = "#2C3E50"    # towers and viewpoints
GREEN = "#2E8B3E"    # camping
BLUE = "#1F6FB2"     # toilets, water
TEAL = "#138D75"     # information
GREY = "#6E7B7F"     # other


def _font(size: int):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def base(color: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, S - 7, S - 7), radius=44, fill=color, outline=W, width=14)
    return img, d


def text(d, s: str, size: int, y: int = S // 2):
    f = _font(size)
    b = d.textbbox((0, 0), s, font=f)
    d.text(((S - (b[2] - b[0])) / 2 - b[0], y - (b[3] - b[1]) / 2 - b[1]), s, fill=W, font=f)


def flame(d, cx: int, by: int, h: int, bg: str | None = None):
    """Flame: a drop (tip up) with a smaller drop in the background colour inside."""

    def drop(cx, by, h, fill):
        r = h * 0.34
        cy = by - r
        tip = (cx, by - h)
        # tangent points on the circle as seen from the tip
        dist = cy - tip[1]
        a = math.asin(min(1.0, r / dist))
        tx = r * math.cos(a)
        ty = r * math.sin(a)
        d.polygon([tip, (cx + tx, cy - ty), (cx - tx, cy - ty)], fill=fill)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)

    drop(cx, by, h, W)
    if bg:
        drop(cx, by - h * 0.06, h * 0.5, bg)


def logs(d, y: int):
    d.line((70, y - 18, 186, y + 18), fill=W, width=LW)
    d.line((70, y + 18, 186, y - 18), fill=W, width=LW)


# --- Icons -----------------------------------------------------------------

def laavu():
    img, d = base(BROWN)
    d.line((40, 196, 216, 196), fill=W, width=LW)               # ground
    d.line((128, 54, 46, 196), fill=W, width=LW + 4)            # roof edges
    d.line((128, 54, 210, 196), fill=W, width=LW + 4)
    d.polygon([(128, 54), (150, 92), (106, 92)], fill=W)        # ridge fill
    d.line((128, 92, 128, 196), fill=W, width=8)                # back wall seam
    flame(d, 128, 192, 56, BROWN)
    return img


def kota():
    img, d = base(BROWN)
    d.polygon([(128, 52), (204, 192), (52, 192)], fill=W)
    d.polygon([(128, 128), (152, 192), (104, 192)], fill=BROWN)  # doorway
    d.line((114, 66, 98, 44), fill=W, width=10)  # smoke hole poles
    d.line((142, 66, 158, 44), fill=W, width=10)
    return img


def tupa():
    img, d = base(BROWN)
    d.polygon([(128, 52), (210, 122), (46, 122)], fill=W)
    d.rectangle((70, 118, 186, 196), fill=W)
    d.rectangle((112, 146, 144, 196), fill=BROWN)  # door
    d.rectangle((158, 66, 176, 100), fill=W)       # chimney
    return img


def nuotiopaikka():
    img, d = base(ORANGE)
    flame(d, 128, 172, 116, ORANGE)
    logs(d, 192)
    return img


def keittokatos():
    img, d = base(ORANGE)
    d.polygon([(128, 46), (214, 104), (42, 104)], fill=W)   # roof
    d.line((66, 104, 66, 196), fill=W, width=LW)           # posts
    d.line((190, 104, 190, 196), fill=W, width=LW)
    flame(d, 128, 188, 66, ORANGE)
    return img


def nakotorni():
    img, d = base(SLATE)
    d.polygon([(100, 48), (156, 48), (172, 80), (84, 80)], fill=W)  # canopy
    d.rectangle((92, 80, 164, 96), fill=W)                          # platform
    d.line((104, 96, 84, 204), fill=W, width=LW)                    # legs
    d.line((152, 96, 172, 204), fill=W, width=LW)
    d.line((100, 130, 160, 170), fill=W, width=10)                  # bracing
    d.line((156, 130, 96, 170), fill=W, width=10)
    return img


def nakoalapaikka():
    img, d = base(SLATE)
    # eye
    d.ellipse((44, 86, 212, 170), outline=W, width=LW)
    d.ellipse((100, 98, 156, 158), fill=W)
    d.ellipse((118, 116, 138, 136), fill=SLATE)
    return img


def telttapaikka():
    img, d = base(GREEN)
    d.polygon([(128, 54), (214, 192), (42, 192)], fill=W)
    d.polygon([(128, 106), (162, 192), (94, 192)], fill=GREEN)
    d.line((30, 196, 226, 196), fill=W, width=LW)
    return img


def kaymala():
    img, d = base(BLUE)
    text(d, "WC", 104)
    return img


def opastuspiste():
    img, d = base(TEAL)
    text(d, "i", 170, y=S // 2 + 4)
    return img


def luontokeskus():
    img, d = base(TEAL)
    # leaf: lens shape at 45° plus midrib
    pts = []
    for i in range(61):
        t = i / 60 * math.pi
        pts.append((math.cos(t) * 80, math.sin(t) * 46))
    pts += [(-x, -y) for x, y in pts[1:-1]]
    c, sn = math.cos(math.radians(-45)), math.sin(math.radians(-45))
    poly = [(128 + x * c - y * sn, 128 + x * sn + y * c) for x, y in pts]
    d.polygon(poly, fill=W)
    d.line((76, 180, 180, 76), fill=TEAL, width=9)
    d.line((60, 196, 84, 172), fill=W, width=12)  # stem
    return img


def puuvaja():
    img, d = base(GREY)
    d.polygon([(128, 50), (210, 104), (46, 104)], fill=W)
    for i, y in enumerate((130, 160, 190)):
        for x in (88, 128, 168):
            d.ellipse((x - 18, y - 16, x + 18, y + 16), fill=W)
            d.ellipse((x - 7, y - 6, x + 7, y + 6), fill=GREY)
    return img


def vesipiste():
    img, d = base(BLUE)
    d.polygon([(128, 46), (176, 136), (80, 136)], fill=W)
    d.ellipse((76, 100, 180, 204), fill=W)
    return img


def rantautumispaikka():
    img, d = base(BLUE)
    # boat
    d.polygon([(40, 140), (216, 140), (186, 184), (70, 184)], fill=W)
    d.line((128, 140, 128, 60), fill=W, width=10)
    d.polygon([(136, 64), (190, 132), (136, 132)], fill=W)
    d.arc((40, 196, 108, 226), 180, 360, fill=W, width=8)
    d.arc((108, 196, 176, 226), 180, 360, fill=W, width=8)
    return img


def pysakointi():
    img, d = base("#2563A8")
    text(d, "P", 170, y=S // 2 + 4)
    return img


ICONS = {
    "laavu.png": laavu, "kota.png": kota, "tupa.png": tupa,
    "nuotiopaikka.png": nuotiopaikka, "keittokatos.png": keittokatos,
    "nakotorni.png": nakotorni, "nakoalapaikka.png": nakoalapaikka,
    "telttapaikka.png": telttapaikka, "kaymala.png": kaymala,
    "opastuspiste.png": opastuspiste, "luontokeskus.png": luontokeskus,
    "puuvaja.png": puuvaja, "vesipiste.png": vesipiste,
    "rantautumispaikka.png": rantautumispaikka, "pysakointi.png": pysakointi,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in ICONS.items():
        fn().resize((OUT_SIZE, OUT_SIZE), Image.LANCZOS).save(OUT / name)
    print(f"{len(ICONS)} kuvaketta -> {OUT}")


if __name__ == "__main__":
    main()
