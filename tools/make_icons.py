#!/usr/bin/env python3
"""Generate the small raster icons used by the front-end.

Run after changing an icon's design::

    python3 tools/make_icons.py

Icons are drawn at 2x the CSS size and downsampled, so they stay crisp on
retina displays. Output lands in ``assets/icons/``.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
INK = (53, 65, 90, 255)          # matches the sidebar/control ink
SUPERSAMPLE = 4                  # draw big, shrink down for smooth curves


def reset_icon(css_px: int = 20, scale: int = 2) -> Image.Image:
    """A counter-clockwise circular arrow — the conventional 'reset' mark."""
    size = css_px * scale
    big = size * SUPERSAMPLE
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = big * 0.17
    width = max(2, int(big * 0.10))
    box = (pad, pad, big - pad, big - pad)

    # Open arc, leaving a gap for the arrowhead.
    draw.arc(box, start=15, end=310, fill=INK, width=width)

    # Arrowhead at the arc's leading end (15 degrees), pointing tangentially.
    r = (big - 2 * pad) / 2
    cx = cy = big / 2
    ang = math.radians(15)
    tipx, tipy = cx + r * math.cos(ang), cy + r * math.sin(ang)
    head = big * 0.17
    draw.polygon(
        [
            (tipx + head * 0.9, tipy - head * 0.15),
            (tipx - head * 0.5, tipy - head * 0.75),
            (tipx - head * 0.15, tipy + head * 0.85),
        ],
        fill=INK,
    )

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    out = ICON_DIR / "reset.png"
    reset_icon().save(out, "PNG", optimize=True)
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
