#!/usr/bin/env python3
"""Generate the site's icons from one vector design.

The mark is a custom serif "L." - a cream L with a gold full stop on Sri Lankan
flag maroon. The same geometry is written out as SVG (browser tab icon) and
rasterised with Pillow at 8x supersampling for the PNG/ICO sizes.

Writes to assets/ (copied to the site root by build_site.py):
  icon.svg               browser tab icon (scalable)
  favicon.ico            16/32/48 px, for older browsers
  apple-touch-icon.png   180 px, iPhone/iPad home screen (full-bleed; iOS rounds the corners)
  icon-192.png           Android / PWA
  icon-512.png           Android / PWA, install screens
  icon-maskable-512.png  Android adaptive icon (artwork inside the safe zone)

Usage:  python make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"

BG_TOP, BG_BOTTOM = (158, 28, 69), (118, 15, 48)  # maroon, lit slightly from above
INK = (251, 247, 239)                              # cream letter
DOT = (242, 182, 58)                               # flag gold
CORNER = 0.2237                                    # iOS-style corner radius, as a share of the side
SS = 8                                             # supersampling factor

# Two weights: "regular" for large icons, "bold" so the strokes survive at 16-32 px.
WEIGHTS = {
    "regular": {"stem": 52, "foot": 20, "serif": 13, "dot": 26},
    "bold": {"stem": 68, "foot": 34, "serif": 22, "dot": 33},
}


# --------------------------------------------------------------------------- #
# Geometry (512 x 512 design space)
# --------------------------------------------------------------------------- #
def letter_path(stem: int, foot: int, serif: int, **_) -> list[tuple]:
    """Outline of a high-contrast serif L with bracketed serifs and a flared beak."""
    top, base, xl = 116, 396, 133
    xr = xl + stem
    ft = base - foot  # top edge of the foot
    t = serif
    return [
        ("M", 107, top), ("H", xr + 40), ("V", top + t),
        ("C", xr + 15, top + t + 1, xr, top + t + 9, xr, top + t + 31),  # top-right bracket
        ("V", ft - 8),
        ("C", xr, ft - 3, xr + 4, ft, xr + 11, ft),                       # inner corner fillet
        ("H", 286),
        ("C", 304, ft, 316, ft - 24, 321, 298),                           # beak, inner curve
        ("H", 327), ("V", base), ("H", 107), ("V", base - t + 1),
        ("C", 122, base - t, xl, base - t - 7, xl, base - t - 24),        # bottom-left bracket
        ("V", top + t + 31),
        ("C", xl, top + t + 11, 118, top + t + 1, 107, top + t),          # top-left bracket
        ("Z",),
    ]


def flatten(cmds: list[tuple], steps: int = 32) -> list[tuple[float, float]]:
    pts, x, y = [], 0.0, 0.0
    for c in cmds:
        op = c[0]
        if op == "M":
            x, y = c[1], c[2]
            pts.append((x, y))
        elif op == "H":
            x = c[1]
            pts.append((x, y))
        elif op == "V":
            y = c[1]
            pts.append((x, y))
        elif op == "C":
            x0, y0 = x, y
            x1, y1, x2, y2, x, y = c[1:]
            for i in range(1, steps + 1):
                u = i / steps
                a, b, cc, d = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3
                pts.append((a * x0 + b * x1 + cc * x2 + d * x, a * y0 + b * y1 + cc * y2 + d * y))
    return pts


def mark(weight: str) -> tuple[list[tuple], list[tuple[float, float]], tuple[float, float, float]]:
    """Letter path, its polygon, and the dot - shifted so the whole mark is optically centred."""
    w = WEIGHTS[weight]
    cmds = letter_path(**w)
    poly = flatten(cmds)
    r = w["dot"]
    dot = (327 + 26 + r, 396 - r, r)  # sits on the baseline, one stem-gap after the beak
    xs = [p[0] for p in poly] + [dot[0] - r, dot[0] + r]
    ys = [p[1] for p in poly] + [dot[1] - r, dot[1] + r]
    dx = 256 - (min(xs) + max(xs)) / 2
    dy = 256 - (min(ys) + max(ys)) / 2 + 4  # a touch low reads as centred
    shift = lambda px, py: (px + dx, py + dy)
    moved = []
    for c in cmds:
        if c[0] in ("M",):
            moved.append(("M", *shift(c[1], c[2])))
        elif c[0] == "H":
            moved.append(("H", c[1] + dx))
        elif c[0] == "V":
            moved.append(("V", c[1] + dy))
        elif c[0] == "C":
            a = shift(c[1], c[2]); b = shift(c[3], c[4]); e = shift(c[5], c[6])
            moved.append(("C", *a, *b, *e))
        else:
            moved.append(c)
    return moved, [shift(*p) for p in poly], (dot[0] + dx, dot[1] + dy, r)


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def render(size: int, weight: str = "regular", rounded: bool = False, scale: float = 1.0) -> Image.Image:
    big = size * SS
    k = big / 512
    img = Image.new("RGBA", (big, big))
    draw = ImageDraw.Draw(img)
    for yy in range(big):  # vertical gradient
        u = yy / (big - 1)
        draw.line([(0, yy), (big, yy)], fill=tuple(round(a + (b - a) * u) for a, b in zip(BG_TOP, BG_BOTTOM)) + (255,))

    _, poly, (cx, cy, r) = mark(weight)
    to_px = lambda x, y: ((256 + (x - 256) * scale) * k, (256 + (y - 256) * scale) * k)
    draw.polygon([to_px(*p) for p in poly], fill=INK + (255,))
    pcx, pcy = to_px(cx, cy)
    pr = r * scale * k
    draw.ellipse([pcx - pr, pcy - pr, pcx + pr, pcy + pr], fill=DOT + (255,))

    if rounded:
        mask = Image.new("L", (big, big), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, big - 1, big - 1], radius=round(big * CORNER), fill=255)
        img.putalpha(mask)
    return img.resize((size, size), Image.LANCZOS)


def svg(weight: str = "bold") -> str:
    cmds, _, (cx, cy, r) = mark(weight)
    d = " ".join(c[0] + ("" if len(c) == 1 else " " + " ".join(f"{v:.1f}".rstrip("0").rstrip(".") for v in c[1:])) for c in cmds)
    rx = round(512 * CORNER)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="rgb{BG_TOP}"/><stop offset="1" stop-color="rgb{BG_BOTTOM}"/>
  </linearGradient></defs>
  <rect width="512" height="512" rx="{rx}" fill="url(#bg)"/>
  <path d="{d}" fill="rgb{INK}"/>
  <circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="rgb{DOT}"/>
</svg>
""".replace(", ", ",")


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "icon.svg").write_text(svg("bold"), encoding="utf-8")
    render(180).convert("RGB").save(ASSETS / "apple-touch-icon.png", optimize=True)
    render(192, rounded=True).save(ASSETS / "icon-192.png", optimize=True)
    render(512, rounded=True).save(ASSETS / "icon-512.png", optimize=True)
    render(512, scale=0.78).convert("RGB").save(ASSETS / "icon-maskable-512.png", optimize=True)
    ico_frames = [render(s, weight="bold", rounded=True) for s in (48, 32, 16)]
    ico_frames[0].save(ASSETS / "favicon.ico", sizes=[(48, 48), (32, 32), (16, 16)], append_images=ico_frames[1:])
    for p in sorted(ASSETS.iterdir()):
        print(f"{p.relative_to(ROOT)}  {p.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
