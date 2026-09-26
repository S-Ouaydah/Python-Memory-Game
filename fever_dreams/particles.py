"""Short-lived effects: sparkles, glow rings, petal bursts and floating text."""

from __future__ import annotations

import math
import random
from functools import lru_cache

import pygame

from . import gfx
from .background import petal_sprite
from .config import Palette
from .tween import ease_out_cubic


@lru_cache(maxsize=32)
def sparkle_sprite(size: int, color: tuple) -> pygame.Surface:
    star = gfx.icon("sparkle", size, color)
    halo = gfx.glow(star, max(2, size // 4), color, strength=1.5)
    pad = (halo.get_width() - size) // 2
    halo.blit(gfx.icon("sparkle", size, (255, 255, 255)), (pad, pad))
    return halo


@lru_cache(maxsize=8)
def ring_texture(color: tuple) -> pygame.Surface:
    d = 160
    base = pygame.Surface((d, d), pygame.SRCALPHA)
    base.fill((*color, 0))
    pygame.draw.circle(base, (*color, 255), (d // 2, d // 2), d // 2 - 14, 5)
    return pygame.transform.gaussian_blur(base, 5)


class Particle:
    __slots__ = (
        "x",
        "y",
        "vx",
        "vy",
        "age",
        "life",
        "sprite",
        "drag",
        "gravity",
        "angle",
        "spin",
        "kind",
        "size",
        "flutter",
        "phase",
    )

    def __init__(self, x, y, vx, vy, life, sprite, kind="spark", drag=2.5, gravity=0.0, spin=0.0, size=1.0) -> None:
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.age, self.life = 0.0, life
        self.sprite, self.kind = sprite, kind
        self.drag, self.gravity = drag, gravity
        self.angle, self.spin = random.uniform(0, 360), spin
        self.size = size
        self.flutter = random.uniform(1.5, 3.0)
        self.phase = random.uniform(0, math.tau)


class FloatingText:
    __slots__ = ("surface", "x", "y", "age", "life", "rise")

    def __init__(self, surface, x, y, life=1.1, rise=48) -> None:
        self.surface, self.x, self.y = surface, x, y
        self.age, self.life, self.rise = 0.0, life, rise


class Effects:
    def __init__(self) -> None:
        self.particles: list[Particle] = []
        self.texts: list[FloatingText] = []
        self.rng = random.Random()

    def clear(self) -> None:
        self.particles.clear()
        self.texts.clear()

    def sparkles(
        self,
        x: float,
        y: float,
        count: int = 18,
        speed: float = 260,
        colors=(Palette.GOLD_LIGHT, Palette.GOLD, (255, 255, 255), Palette.ROSE),
        scale: float = 1.0,
    ) -> None:
        for _ in range(count):
            angle = self.rng.uniform(0, math.tau)
            v = self.rng.uniform(0.35, 1.0) * speed
            size = int(self.rng.choice((12, 14, 18, 24)) * scale)
            sprite = sparkle_sprite(max(4, size), self.rng.choice(colors))
            self.particles.append(
                Particle(
                    x,
                    y,
                    math.cos(angle) * v,
                    math.sin(angle) * v,
                    self.rng.uniform(0.5, 0.95),
                    sprite,
                    drag=3.2,
                    gravity=60,
                    spin=self.rng.uniform(-200, 200),
                )
            )

    def ring(self, x: float, y: float, radius: float, color=Palette.GOLD_LIGHT, life=0.7) -> None:
        p = Particle(x, y, 0, 0, life, ring_texture(tuple(color)), kind="ring", size=radius)
        self.particles.append(p)

    def petal_burst(
        self,
        x: float,
        y: float,
        count: int = 60,
        speed: float = 520,
        spread: float = math.tau,
        direction: float = -math.pi / 2,
    ) -> None:
        for _ in range(count):
            angle = direction + self.rng.uniform(-spread / 2, spread / 2)
            v = self.rng.uniform(0.3, 1.0) * speed
            sprite = petal_sprite(self.rng.randint(9, 20), self.rng.choice(Palette.PETALS))
            self.particles.append(
                Particle(
                    x,
                    y,
                    math.cos(angle) * v,
                    math.sin(angle) * v,
                    self.rng.uniform(2.2, 3.6),
                    sprite,
                    kind="petal",
                    drag=1.6,
                    gravity=110,
                    spin=self.rng.uniform(-240, 240),
                )
            )

    def text(self, surface: pygame.Surface, x: float, y: float, life=1.1, rise=48) -> None:
        self.texts.append(FloatingText(surface, x, y, life, rise))

    def update(self, dt: float) -> None:
        alive = []
        for p in self.particles:
            p.age += dt
            if p.age >= p.life:
                continue
            damp = math.exp(-p.drag * dt)
            p.vx *= damp
            p.vy = p.vy * damp + p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.angle += p.spin * dt
            alive.append(p)
        self.particles = alive
        for t in self.texts:
            t.age += dt
        self.texts = [t for t in self.texts if t.age < t.life]

    def draw(self, surface: pygame.Surface) -> None:
        for p in self.particles:
            k = p.age / p.life
            if p.kind == "ring":
                d = max(2, int(p.size * 2 * (0.35 + 0.65 * ease_out_cubic(k))))
                img = pygame.transform.smoothscale(p.sprite, (d, d))
                gfx.blit_center(surface, img, (p.x, p.y), (1 - k) ** 1.5)
            elif p.kind == "petal":
                sw, sh = p.sprite.get_size()
                squash = abs(math.cos(p.age * p.flutter * 2 + p.phase))
                img = pygame.transform.scale(p.sprite, (max(1, int(sw * (0.25 + 0.75 * squash))), sh))
                img = pygame.transform.rotate(img, p.angle)
                gfx.blit_center(surface, img, (p.x, p.y), min(1.0, (1 - k) * 2.5) * 0.95)
            else:
                img = pygame.transform.rotate(p.sprite, p.angle)
                grow = 1 - k * 0.5
                if grow < 0.98:
                    w, h = img.get_size()
                    img = pygame.transform.smoothscale(img, (max(1, int(w * grow)), max(1, int(h * grow))))
                gfx.blit_center(surface, img, (p.x, p.y), min(1.0, (1 - k) * 1.8))
        for t in self.texts:
            k = t.age / t.life
            y = t.y - t.rise * ease_out_cubic(k)
            alpha = min(1.0, k * 6) * (1 - max(0.0, (k - 0.6) / 0.4))
            gfx.blit_center(surface, t.surface, (t.x, y), alpha)
