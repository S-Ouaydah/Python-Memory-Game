"""Drawing helpers: anti-aliased shapes, gradients, glows, text and icons.

pygame's primitives are aliased, so shapes are drawn at ``SS``x resolution
and smooth-scaled down. Transparent pixels are always filled with the shape's
own colour first: smoothscale and blur treat every channel independently, so
a transparent-black background would leave dark fringes around edges.

Most helpers are cached; the surfaces they return are shared and must not be
modified by callers (use :func:`blit_alpha` to fade them).
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Iterable, Sequence
from functools import lru_cache

import pygame

SS = 4

Color = tuple  # (r, g, b) or (r, g, b, a)


def rgba(color: Color, alpha: int | None = None) -> tuple[int, int, int, int]:
    if alpha is None:
        alpha = color[3] if len(color) > 3 else 255
    return (int(color[0]), int(color[1]), int(color[2]), int(alpha))


def blit_alpha(dest: pygame.Surface, src: pygame.Surface, pos, alpha: float) -> None:
    """Blit a (possibly shared) surface faded to ``alpha`` in [0, 1]."""
    if alpha <= 0.004:
        return
    if alpha >= 0.996:
        dest.blit(src, pos)
        return
    src.set_alpha(int(alpha * 255))
    dest.blit(src, pos)
    src.set_alpha(255)


def blit_center(dest: pygame.Surface, src: pygame.Surface, center, alpha: float = 1.0) -> None:
    w, h = src.get_size()
    blit_alpha(dest, src, (round(center[0] - w / 2), round(center[1] - h / 2)), alpha)


def tint(surface: pygame.Surface, color: Color) -> pygame.Surface:
    """A copy of ``surface`` in a single colour, keeping its alpha."""
    out = surface.copy()
    out.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
    out.fill((*color[:3], 0), special_flags=pygame.BLEND_RGBA_ADD)
    return out


def multiply_alpha(surface: pygame.Surface, factor: float) -> pygame.Surface:
    out = surface.copy()
    out.fill((255, 255, 255, int(255 * factor)), special_flags=pygame.BLEND_RGBA_MULT)
    return out


# -- shapes ------------------------------------------------------------------


@lru_cache(maxsize=1024)
def rounded_rect(
    size: tuple[int, int],
    radius: int,
    color: Color,
    border: int = 0,
    border_color: Color | None = None,
) -> pygame.Surface:
    """Anti-aliased rounded rectangle, optionally with a border."""
    w, h = max(1, int(size[0])), max(1, int(size[1]))
    big = pygame.Surface((w * SS, h * SS), pygame.SRCALPHA)
    outer = border_color if border and border_color else color
    big.fill((*outer[:3], 0))
    r = max(0, int(radius * SS))
    rect = big.get_rect()
    pygame.draw.rect(big, rgba(outer), rect, border_radius=r)
    if border and border_color:
        inner = rect.inflate(-2 * border * SS, -2 * border * SS)
        pygame.draw.rect(big, rgba(color), inner, border_radius=max(0, r - border * SS))
    return pygame.transform.smoothscale(big, (w, h))


@lru_cache(maxsize=256)
def rounded_outline(size: tuple[int, int], radius: int, color: Color, width: float) -> pygame.Surface:
    """Anti-aliased rounded rectangle outline with a transparent middle."""
    w, h = max(1, int(size[0])), max(1, int(size[1]))
    big = pygame.Surface((w * SS, h * SS), pygame.SRCALPHA)
    big.fill((*color[:3], 0))
    r = max(0, int(radius * SS))
    rect = big.get_rect()
    pygame.draw.rect(big, rgba(color), rect, border_radius=r)
    stroke = max(1, int(width * SS))
    pygame.draw.rect(big, (*color[:3], 0), rect.inflate(-2 * stroke, -2 * stroke), border_radius=max(0, r - stroke))
    return pygame.transform.smoothscale(big, (w, h))


@lru_cache(maxsize=256)
def circle(diameter: int, color: Color) -> pygame.Surface:
    d = max(1, int(diameter))
    big = pygame.Surface((d * SS, d * SS), pygame.SRCALPHA)
    big.fill((*color[:3], 0))
    pygame.draw.circle(big, rgba(color), (d * SS // 2, d * SS // 2), d * SS // 2)
    return pygame.transform.smoothscale(big, (d, d))


def _interp_stops(stops: Sequence[tuple[float, Color]], t: float) -> tuple[int, int, int, int]:
    if t <= stops[0][0]:
        return rgba(stops[0][1])
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            k = 0.0 if p1 == p0 else (t - p0) / (p1 - p0)
            a, b = rgba(c0), rgba(c1)
            return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(4))
    return rgba(stops[-1][1])


@lru_cache(maxsize=128)
def gradient(size: tuple[int, int], stops: tuple[tuple[float, Color], ...], vertical: bool = True) -> pygame.Surface:
    """Linear multi-stop gradient; ``stops`` are ``(position, colour)`` pairs."""
    w, h = max(1, int(size[0])), max(1, int(size[1]))
    n = h if vertical else w
    line = pygame.Surface((1, n) if vertical else (n, 1), pygame.SRCALPHA)
    for i in range(n):
        color = _interp_stops(stops, i / max(1, n - 1))
        line.set_at((0, i) if vertical else (i, 0), color)
    return pygame.transform.scale(line, (w, h))


@lru_cache(maxsize=128)
def rounded_gradient(
    size: tuple[int, int], radius: int, stops: tuple[tuple[float, Color], ...], vertical: bool = True
) -> pygame.Surface:
    surf = gradient(size, stops, vertical).copy()
    surf.blit(rounded_rect(size, radius, (255, 255, 255)), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return surf


@lru_cache(maxsize=64)
def radial_glow(diameter: int, color: Color, falloff: float = 2.2) -> pygame.Surface:
    """Opaque black square with a soft coloured disc, for additive blending."""
    base = 128
    small = pygame.Surface((base, base))
    small.fill((0, 0, 0))
    half = base / 2
    steps = 48
    for i in range(steps, 0, -1):
        r = half * i / steps
        k = (1 - i / steps) ** falloff
        pygame.draw.circle(small, tuple(int(c * k) for c in color[:3]), (half, half), r)
    small = pygame.transform.box_blur(small, 3)
    d = max(2, int(diameter))
    return pygame.transform.smoothscale(small, (d, d))


@lru_cache(maxsize=64)
def soft_blob(diameter: int, color: Color, alpha: int = 160, falloff: float = 1.8) -> pygame.Surface:
    """A translucent disc fading to nothing at its edge, for normal alpha blending."""
    base = 128
    small = pygame.Surface((base, base), pygame.SRCALPHA)
    small.fill((*color[:3], 0))
    half = base / 2
    steps = 48
    for i in range(steps, 0, -1):  # inner circles overwrite outer ones
        k = (1 - i / steps) ** falloff
        pygame.draw.circle(small, (*color[:3], int(alpha * k)), (half, half), half * i / steps)
    small = pygame.transform.box_blur(small, 3)
    d = max(2, int(diameter))
    return pygame.transform.smoothscale(small, (d, d))


def soft_shadow(
    size: tuple[int, int], radius: int, blur: int, alpha: int = 150, color: Color = (0, 0, 0)
) -> pygame.Surface:
    """A blurred rounded rectangle, padded by ``2 * blur`` on every side."""
    return _soft_shape(int(size[0]), int(size[1]), int(radius), int(blur), int(alpha), tuple(color[:3]))


@lru_cache(maxsize=256)
def _soft_shape(w: int, h: int, radius: int, blur: int, alpha: int, color: tuple) -> pygame.Surface:
    pad = blur * 2
    surf = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
    surf.fill((*color, 0))
    pygame.draw.rect(surf, (*color, alpha), (pad, pad, w, h), border_radius=radius)
    if blur > 0:
        surf = pygame.transform.gaussian_blur(surf, blur)
    return surf


def glow(surface: pygame.Surface, radius: int, color: Color, strength: float = 1.0) -> pygame.Surface:
    """Blurred single-colour silhouette of ``surface``, padded by ``2 * radius``."""
    pad = radius * 2
    w, h = surface.get_size()
    out = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
    out.fill((*color[:3], 0))
    out.blit(tint(surface, color), (pad, pad))
    out = pygame.transform.gaussian_blur(out, radius)
    if strength != 1.0:
        # Boost by stacking, or fade by scaling alpha.
        if strength > 1.0:
            base = out.copy()
            for _ in range(int(strength) - 1):
                out.blit(base, (0, 0))
        else:
            out = multiply_alpha(out, strength)
    return out


# -- text --------------------------------------------------------------------

_text_cache: OrderedDict = OrderedDict()
_TEXT_CACHE_SIZE = 600


def text(font: pygame.font.Font, string: str, color: Color, tracking: float = 0.0) -> pygame.Surface:
    """Render text (cached). ``tracking`` adds letter spacing in pixels."""
    key = (id(font), string, tuple(color), tracking)
    cached = _text_cache.get(key)
    if cached is not None:
        _text_cache.move_to_end(key)
        return cached
    if not tracking or len(string) < 2:
        surf = font.render(string, True, color)
    else:
        xs = [font.size(string[:i])[0] + tracking * i for i in range(len(string))]
        last = font.size(string[-1])[0]
        surf = pygame.Surface((int(xs[-1] + last + 2), font.get_height()), pygame.SRCALPHA)
        surf.fill((*color[:3], 0))
        for x, ch in zip(xs, string):
            if not ch.isspace():
                surf.blit(font.render(ch, True, color), (round(x), 0))
    _text_cache[key] = surf
    if len(_text_cache) > _TEXT_CACHE_SIZE:
        _text_cache.popitem(last=False)
    return surf


def gradient_text(
    font: pygame.font.Font, string: str, stops, tracking: float = 0.0, vertical: bool = True
) -> pygame.Surface:
    base = text(font, string, (255, 255, 255), tracking).copy()
    base.blit(gradient(base.get_size(), tuple(stops), vertical), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return base


def wrap_lines(font: pygame.font.Font, string: str, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in string.split("\n"):
        words = paragraph.split()
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if font.size(candidate)[0] <= width or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# -- icons -------------------------------------------------------------------


def _poly(big, color, pts: Iterable[tuple[float, float]], k: float) -> None:
    pygame.draw.polygon(big, color, [(x * k, y * k) for x, y in pts])


def _stroke(big, color, pts, k: float, width: float) -> None:
    """Polyline with round caps and joins."""
    scaled = [(x * k, y * k) for x, y in pts]
    w = max(1, int(width * k))
    pygame.draw.lines(big, color, False, scaled, w)
    for p in scaled:
        pygame.draw.circle(big, color, p, w / 2)


def _ring(big, color, clear, center, r_outer, r_inner, k):
    c = (center[0] * k, center[1] * k)
    pygame.draw.circle(big, color, c, r_outer * k)
    pygame.draw.circle(big, clear, c, r_inner * k)


@lru_cache(maxsize=256)
def icon(name: str, size: int, color: Color) -> pygame.Surface:
    """Small vector icons drawn on a 24x24 grid."""
    size = max(4, int(size))
    big = pygame.Surface((size * SS, size * SS), pygame.SRCALPHA)
    clear = (*color[:3], 0)
    big.fill(clear)
    col = rgba(color)
    k = size * SS / 24

    if name == "pause":
        pygame.draw.rect(big, col, (6.5 * k, 5 * k, 3.6 * k, 14 * k), border_radius=int(1.2 * k))
        pygame.draw.rect(big, col, (13.9 * k, 5 * k, 3.6 * k, 14 * k), border_radius=int(1.2 * k))
    elif name == "play":
        _poly(big, col, [(8, 5), (19.5, 12), (8, 19)], k)
    elif name == "restart":
        _ring(big, col, clear, (12, 12.5), 8.2, 6.0, k)
        _poly(big, clear, [(12, 12.5), (13, 0), (24, 0), (24, 9)], k)
        _poly(big, col, [(11.2, 1.2), (17.2, 4.6), (11.6, 8.6)], k)
    elif name == "eye":
        top = [(2 + 20 * t / 24, 12 - 7.2 * math.sin(math.pi * t / 24)) for t in range(25)]
        bottom = [(22 - 20 * t / 24, 12 + 7.2 * math.sin(math.pi * t / 24)) for t in range(25)]
        _poly(big, col, top + bottom, k)
        inner_top = [(4.6 + 14.8 * t / 24, 12 - 5.0 * math.sin(math.pi * t / 24)) for t in range(25)]
        inner_bottom = [(19.4 - 14.8 * t / 24, 12 + 5.0 * math.sin(math.pi * t / 24)) for t in range(25)]
        _poly(big, clear, inner_top + inner_bottom, k)
        pygame.draw.circle(big, col, (12 * k, 12 * k), 3.4 * k)
    elif name == "gear":
        pts = []
        teeth = 8
        for i in range(teeth * 4):
            angle = math.tau * i / (teeth * 4) - math.pi / 2
            radius = 10.4 if (i % 4) in (1, 2) else 7.6
            pts.append((12 + radius * math.cos(angle), 12 + radius * math.sin(angle)))
        _poly(big, col, pts, k)
        pygame.draw.circle(big, clear, (12 * k, 12 * k), 3.4 * k)
    elif name == "home":
        _poly(big, col, [(12, 3), (21.5, 11), (19, 11), (19, 20.5), (5, 20.5), (5, 11), (2.5, 11)], k)
        pygame.draw.rect(big, clear, (10 * k, 14 * k, 4 * k, 6.6 * k), border_radius=int(0.8 * k))
    elif name == "close":
        _stroke(big, col, [(6.5, 6.5), (17.5, 17.5)], k, 2.4)
        _stroke(big, col, [(17.5, 6.5), (6.5, 17.5)], k, 2.4)
    elif name == "star":
        pts = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = 10.8 if i % 2 == 0 else 4.6
            pts.append((12 + radius * math.cos(angle), 12.8 + radius * math.sin(angle)))
        _poly(big, col, pts, k)
    elif name == "check":
        _stroke(big, col, [(5, 12.5), (10, 17.5), (19.5, 7)], k, 2.8)
    elif name in ("sound", "sound_off"):
        if name == "sound":
            _ring(big, col, clear, (12.5, 12), 5.6, 3.9, k)
            _ring(big, col, clear, (12.5, 12), 9.6, 7.9, k)
            _poly(big, clear, [(12.5, 12), (0, -4), (12.5, -4), (12.5, 28), (0, 28)], k)
        _poly(big, col, [(3, 9), (7.5, 9), (12.5, 4.5), (12.5, 19.5), (7.5, 15), (3, 15)], k)
        if name == "sound_off":
            _stroke(big, col, [(15.5, 9), (21, 15)], k, 2.2)
            _stroke(big, col, [(21, 9), (15.5, 15)], k, 2.2)
    elif name == "arrow_right":
        _stroke(big, col, [(4.5, 12), (18.5, 12)], k, 2.4)
        _stroke(big, col, [(12.5, 6), (18.5, 12), (12.5, 18)], k, 2.4)
    elif name == "fullscreen":
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            cx, cy = 12 - 7.5 * sx, 12 - 7.5 * sy
            _stroke(big, col, [(cx, cy + 5 * sy), (cx, cy), (cx + 5 * sx, cy)], k, 2.2)
    elif name == "sparkle":
        _poly(big, col, [(12, 2), (14, 10), (22, 12), (14, 14), (12, 22), (10, 14), (2, 12), (10, 10)], k)
    elif name == "book":
        _poly(big, col, [(2.5, 5), (10.5, 5.5), (12, 7), (12, 20), (10.5, 18.8), (2.5, 18.5)], k)
        _poly(big, col, [(21.5, 5), (13.5, 5.5), (12, 7), (12, 20), (13.5, 18.8), (21.5, 18.5)], k)
        _stroke(big, clear, [(12, 6), (12, 21)], k, 1.2)
    elif name == "users":
        pygame.draw.circle(big, col, (16 * k, 7.6 * k), 3.3 * k)
        pygame.draw.ellipse(big, col, (10.5 * k, 12.6 * k, 11 * k, 13 * k))
        pygame.draw.circle(big, clear, (9 * k, 9 * k), 5.2 * k)
        pygame.draw.ellipse(big, clear, (1.2 * k, 13.6 * k, 15.6 * k, 15 * k))
        pygame.draw.circle(big, col, (9 * k, 9 * k), 3.6 * k)
        pygame.draw.ellipse(big, col, (3 * k, 15.4 * k, 12 * k, 13 * k))
    elif name == "trophy":
        _ring(big, col, clear, (6.5, 7.5), 3.6, 2.0, k)
        _ring(big, col, clear, (17.5, 7.5), 3.6, 2.0, k)
        _poly(
            big,
            col,
            [
                (6.5, 3.5),
                (17.5, 3.5),
                (17, 10),
                (14.5, 13.5),
                (13, 14.5),
                (13, 17),
                (16, 17.5),
                (16.5, 20.5),
                (7.5, 20.5),
                (8, 17.5),
                (11, 17),
                (11, 14.5),
                (9.5, 13.5),
                (7, 10),
            ],
            k,
        )
    else:
        raise ValueError(f"unknown icon {name!r}")

    return pygame.transform.smoothscale(big, (size, size))
