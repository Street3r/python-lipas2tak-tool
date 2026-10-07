"""Tekee väliaikaiset kuvakkeet (icons/placeholder/*.png).

Nämä korvataan Metsähallituksen symboleilla, jos käyttölupa saadaan.
Ajo: python scripts/make_placeholder_icons.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "icons" / "placeholder"

# kuvake: (lyhenne, taustaväri)
ICONS = {
    "laavu.png": ("L", "#6B4226"),
    "kota.png": ("K", "#6B4226"),
    "tupa.png": ("T", "#6B4226"),
    "nuotiopaikka.png": ("N", "#D35400"),
    "keittokatos.png": ("KK", "#D35400"),
    "nakotorni.png": ("NT", "#2C3E50"),
    "nakoalapaikka.png": ("NÄ", "#2C3E50"),
    "telttapaikka.png": ("TP", "#27AE60"),
    "kaymala.png": ("WC", "#2980B9"),
    "opastuspiste.png": ("i", "#16A085"),
    "luontokeskus.png": ("LK", "#16A085"),
    "puuvaja.png": ("PV", "#7F8C8D"),
    "vesipiste.png": ("V", "#3498DB"),
    "rantautumispaikka.png": ("R", "#1F6FD1"),
    "pysakointi.png": ("P", "#34495E"),
}

SIZE = 64

# Fontti, jossa on ä/ö (Pillowin oletusfontista ne puuttuvat)
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _font(size: int):
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # vanha Pillow
        return ImageFont.load_default()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (text, color) in ICONS.items():
        img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((2, 2, SIZE - 3, SIZE - 3), radius=12, fill=color, outline="white", width=4)
        size = 34 if len(text) == 1 else 24
        font = _font(size)
        bbox = d.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((SIZE - w) / 2 - bbox[0], (SIZE - h) / 2 - bbox[1]), text, fill="white", font=font)
        img.save(OUT / name)
    print(f"{len(ICONS)} kuvaketta -> {OUT}")


if __name__ == "__main__":
    main()
