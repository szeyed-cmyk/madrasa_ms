"""1.0.5 branding: turn the two brand colours from Settings > Branding into CSS variables.

static/app.css is built with Tailwind colours "brand" (= primary, also used for the old `emerald` classes)
and "accent" (= secondary) that read `rgb(var(--brand-500) / <alpha>)`. _base.html prints the variables
from shades(), so a new colour applies to every page without rebuilding the CSS.
"""

from __future__ import annotations

import re

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
# Mix factors: >0 = towards white, <0 = towards black (500 = the chosen colour itself)
STEPS = {
    50: 0.92,
    100: 0.84,
    200: 0.68,
    300: 0.48,
    400: 0.24,
    500: 0.0,
    600: -0.12,
    700: -0.28,
    800: -0.42,
    900: -0.55,
    950: -0.7,
}


def valid_hex(value: str | None) -> bool:
    return bool(value and HEX_RE.match(value))


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def shades(hex_color: str) -> dict[int, str]:
    """{50: "236 253 245", ..., 950: "..."} as space-separated RGB for rgb(var(--x) / a)."""
    r, g, b = _rgb(hex_color)
    out = {}
    for step, f in STEPS.items():
        if f >= 0:
            c = [round(v + (255 - v) * f) for v in (r, g, b)]
        else:
            c = [round(v * (1 + f)) for v in (r, g, b)]
        out[step] = " ".join(str(max(0, min(255, v))) for v in c)
    return out


def css_vars(primary: str, secondary: str) -> str:
    lines = [f"--brand-{k}:{v}" for k, v in shades(primary).items()]
    lines += [f"--accent-{k}:{v}" for k, v in shades(secondary).items()]
    return ":root{" + ";".join(lines) + "}"
