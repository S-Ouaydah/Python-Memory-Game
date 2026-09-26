"""The living backdrop shared by every scene: aurora glows, petals and motes."""

from __future__ import annotations

import math
import random
from functools import lru_cache

import pygame

from . import gfx
from .config import Palette


@lru_cache(maxsize=64)
def petal_sprite(size: int, color: tuple) -> pygame.Surface:
    """A cherry-blossom petal: a soft teardrop with a notch at the tip."""
    size = max(4, int(size))
    w, h = size, int(size * 1.25)
    ss = 6
    big = pygame.Surface((w * ss, h * ss), pygame.SRCALPHA)
    big.fill((*color, 0))
    pygame.draw.ellipse(big, (*color, 255), (0, int(h * ss * 0.08), w * ss, int(h * ss * 0.92)))
    pygame.draw.polygon(big, (*color, 0), [(w * ss * 0.5, h * ss * 0.2), (w * ss * 0.36, 0), (w * ss * 0.64, 0)])
    light = tuple(min(255, c + 30) for c in color)
    pygame.draw.ellipse(big, (*light, 255), (w * ss * 0.3, h * ss * 0.4, w * ss * 0.4, h * ss * 0.45))
    surf = pygame.transform.smoothscale(big, (w, h))
    return pygame.transform.gaussian_blur(surf, 1) if size > 10 else surf


@lru_cache(maxsize=16)
def mote_sprite(diameter: int, color: tuple) -> pygame.Surface:
    d = max(2, int(diameter))
    return gfx.glow(gfx.circle(d, color), max(2, d), color, strength=2.0)


def make_vignette(size: tuple[int, int], strength: int = 185) -> pygame.Surface:
    sw, sh = 96, 60
    small = pygame.Surface((sw, sh), pygame.SRCALPHA)
    for y in range(sh):
        dy = (y + 0.5) / sh * 2 - 1
        for x in range(sw):
            dx = (x + 0.5) / sw * 2 - 1
            d = math.sqrt(dx * dx * 0.85 + dy * dy * 1.1)
            a = max(0.0, min(1.0, (d - 0.5) / 0.8)) ** 1.7
            small.set_at((x, y), (6, 3, 14, int(a * strength)))
    return pygame.transform.smoothscale(small, size)


class Petal:
    __slots__ = ("x", "y", "depth", "vx", "vy", "angle", "spin", "phase", "flutter", "sprite")

    def __init__(self, rng: random.Random, w: int, h: int, anywhere: bool) -> None:
        self.depth = rng.uniform(0.25, 1.0)
        size = int(7 + 13 * self.depth)
        self.sprite = petal_sprite(size, rng.choice(Palette.PETALS))
        self.x = rng.uniform(-0.1, 1.0) * w if anywhere else rng.uniform(-0.3, 0.9) * w
        self.y = rng.uniform(0, h) if anywhere else rng.uniform(-80, -20)
        self.vx = rng.uniform(14, 34) * (0.5 + self.depth)
        self.vy = rng.uniform(22, 44) * (0.5 + self.depth)
        self.angle = rng.uniform(0, 360)
        self.spin = rng.uniform(-80, 80)
        self.phase = rng.uniform(0, math.tau)
        self.flutter = rng.uniform(1.2, 2.6)


class Mote:
    __slots__ = ("x", "y", "vy", "phase", "speed", "sprite", "sway")

    def __init__(self, rng: random.Random, w: int, h: int) -> None:
        self.x = rng.uniform(0, w)
        self.y = rng.uniform(0, h)
        self.vy = -rng.uniform(4, 14)
        self.phase = rng.uniform(0, math.tau)
        self.speed = rng.uniform(0.6, 1.8)
        self.sway = rng.uniform(4, 14)
        color = rng.choice((Palette.GOLD_LIGHT, (255, 255, 255), Palette.ROSE, Palette.LAVENDER))
        self.sprite = mote_sprite(rng.choice((2, 2, 3, 4)), color)


class Blob:
    __slots__ = ("color", "scale", "cx", "cy", "ax", "ay", "fx", "fy", "phase", "surf")

    def __init__(self, color, scale, cx, cy, ax, ay, fx, fy, phase) -> None:
        self.color, self.scale = color, scale
        self.cx, self.cy, self.ax, self.ay = cx, cy, ax, ay
        self.fx, self.fy, self.phase = fx, fy, phase
        self.surf: pygame.Surface | None = None


class DreamBackground:
    PETAL_COUNT = 30
    MOTE_COUNT = 46

    def __init__(self, size: tuple[int, int], rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.time = 0.0
        self.ambient = True
        #: Extra brightness pulse (e.g. on a match); decays by itself.
        self.flash = 0.0
        self.blobs = [
            Blob((80, 50, 134), 0.95, 0.22, 0.30, 0.10, 0.08, 0.045, 0.061, 0.0),
            Blob((140, 54, 108), 0.85, 0.80, 0.25, 0.09, 0.10, 0.052, 0.037, 1.7),
            Blob((44, 78, 146), 0.80, 0.70, 0.85, 0.12, 0.07, 0.033, 0.049, 3.1),
            Blob((122, 70, 80), 0.60, 0.25, 0.92, 0.10, 0.06, 0.041, 0.057, 4.4),
            Blob((60, 30, 92), 0.70, 0.50, 0.55, 0.16, 0.12, 0.027, 0.031, 5.2),
        ]
        self.petals: list[Petal] = []
        self.motes: list[Mote] = []
        self.resize(size)

    def resize(self, size: tuple[int, int]) -> None:
        w, h = self.size = (max(1, size[0]), max(1, size[1]))
        stops = ((0.0, Palette.BG_TOP), (0.55, Palette.BG_MID), (1.0, Palette.BG_BOTTOM))
        self.base = gfx.gradient((w, h), stops).convert()
        self.vignette = make_vignette((w, h)).convert_alpha()
        span = max(w, h)
        for blob in self.blobs:
            blob.surf = gfx.radial_glow(int(span * blob.scale), blob.color).convert()
        self.petals = [Petal(self.rng, w, h, anywhere=True) for _ in range(self.PETAL_COUNT)]
        self.motes = [Mote(self.rng, w, h) for _ in range(self.MOTE_COUNT)]

    def update(self, dt: float) -> None:
        self.time += dt
        self.flash = max(0.0, self.flash - dt * 1.6)
        if not self.ambient:
            return
        w, h = self.size
        t = self.time
        for i, p in enumerate(self.petals):
            p.x += (p.vx + math.sin(t * 0.7 + p.phase) * 18 * p.depth) * dt
            p.y += p.vy * dt
            p.angle += p.spin * dt
            if p.y > h + 40 or p.x > w + 40:
                self.petals[i] = Petal(self.rng, w, h, anywhere=False)
        for m in self.motes:
            m.y += m.vy * dt
            if m.y < -10:
                m.y = h + 10
                m.x = self.rng.uniform(0, w)

    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self.base, (0, 0))
        w, h = self.size
        t = self.time
        for blob in self.blobs:
            bw = blob.surf.get_width()
            x = (blob.cx + blob.ax * math.sin(t * blob.fx * math.tau + blob.phase)) * w
            y = (blob.cy + blob.ay * math.cos(t * blob.fy * math.tau + blob.phase)) * h
            surface.blit(blob.surf, (x - bw / 2, y - bw / 2), special_flags=pygame.BLEND_RGB_ADD)
        if self.flash > 0:
            surface.fill(tuple(int(c * self.flash * 0.18) for c in Palette.GOLD), special_flags=pygame.BLEND_RGB_ADD)
        if self.ambient:
            for m in self.motes:
                twinkle = 0.5 + 0.5 * math.sin(t * m.speed * 2 + m.phase)
                x = m.x + math.sin(t * 0.5 + m.phase) * m.sway
                gfx.blit_alpha(surface, m.sprite, (x, m.y), 0.15 + 0.7 * twinkle)
            for p in self.petals:
                self.draw_petal(surface, p, t)
        surface.blit(self.vignette, (0, 0))

    @staticmethod
    def draw_petal(surface: pygame.Surface, p: Petal, t: float, alpha: float | None = None) -> None:
        sw, sh = p.sprite.get_size()
        squash = abs(math.cos(t * p.flutter + p.phase))
        img = pygame.transform.scale(p.sprite, (max(1, int(sw * (0.25 + 0.75 * squash))), sh))
        img = pygame.transform.rotate(img, p.angle)
        a = (0.25 + 0.6 * p.depth) if alpha is None else alpha
        gfx.blit_center(surface, img, (p.x, p.y), a)
