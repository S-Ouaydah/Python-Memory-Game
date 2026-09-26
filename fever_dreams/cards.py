"""On-screen card: flip, lift, glow, shake and deal animations."""

from __future__ import annotations

import math

import pygame

from . import gfx
from .assets import CardArt, card_radius
from .config import DEAL_DURATION, FLIP_DURATION, Palette
from .tween import approach, bump, ease_in_out_cubic, ease_out_back, ease_out_cubic, lerp, step_toward

MATCH_PULSE = 0.55
SHAKE_TIME = 0.55
WAVE_TIME = 0.6


def _fit(surface: pygame.Surface, size: tuple[int, int]) -> pygame.Surface:
    if surface.get_size() == size:
        return surface
    return pygame.transform.smoothscale(surface, size)


class CardSprite:
    def __init__(self, index: int, face: int, art: CardArt) -> None:
        self.index = index
        self.face = face
        self.art = art
        self.rect = pygame.Rect(0, 0, 1, 1)  # resting place on the board
        self.face_up = False
        self.flip = 0.0  # 0 = showing the back, 1 = showing the face
        self.flip_speed = 1.0
        self.hover = 0.0
        self.focus = 0.0
        self.matched = False
        self.match_color = Palette.GOLD
        self.dim = 0.0
        # Seconds since each effect started (negative while delayed); None = inactive.
        self.match_age: float | None = None
        self.shake_age: float | None = None
        self.wave_age: float | None = None
        self.deal_age = DEAL_DURATION  # finished unless deal() is called
        self.deal_from = (0.0, 0.0)

    # -- commands ------------------------------------------------------------

    def turn(self, face_up: bool, speed: float = 1.0) -> None:
        self.face_up = face_up
        self.flip_speed = speed

    def mark_matched(self, color=Palette.GOLD) -> None:
        self.matched = True
        self.match_color = tuple(color)
        self.match_age = 0.0

    def shake(self) -> None:
        self.shake_age = 0.0

    def wave(self, delay: float) -> None:
        self.wave_age = -delay

    def deal(self, origin: tuple[float, float], delay: float) -> None:
        self.deal_from = origin
        self.deal_age = -delay

    def finish_deal(self) -> None:
        self.deal_age = DEAL_DURATION

    # -- state ---------------------------------------------------------------

    @property
    def dealing(self) -> bool:
        return self.deal_age < DEAL_DURATION

    @property
    def turning(self) -> bool:
        return self.flip != (1.0 if self.face_up else 0.0)

    def update(self, dt: float, hovered: bool, focused: bool) -> None:
        target = 1.0 if self.face_up else 0.0
        self.flip = step_toward(self.flip, target, dt * self.flip_speed / FLIP_DURATION)
        self.hover = approach(self.hover, 1.0 if hovered else 0.0, 16, dt)
        self.focus = approach(self.focus, 1.0 if focused else 0.0, 18, dt)
        if self.match_age is not None:
            self.match_age += dt
            if self.match_age > MATCH_PULSE:
                self.dim = approach(self.dim, 1.0, 2.2, dt)
        if self.shake_age is not None:
            self.shake_age = self.shake_age + dt if self.shake_age < SHAKE_TIME else None
        if self.wave_age is not None:
            self.wave_age = self.wave_age + dt if self.wave_age < WAVE_TIME else None
        if self.deal_age < DEAL_DURATION:
            self.deal_age += dt

    # -- drawing -------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        x, y, w, h = self.rect
        if self.deal_age < 0:
            return
        shown = ease_in_out_cubic(self.flip)
        squash = abs(math.cos(math.pi * shown))
        front = shown >= 0.5
        lift = bump(shown)

        scale = 1.0 + 0.07 * lift + 0.035 * self.hover
        if self.match_age is not None and self.match_age < MATCH_PULSE:
            scale += 0.09 * bump(self.match_age / MATCH_PULSE)
        if self.wave_age is not None and self.wave_age >= 0:
            scale += 0.07 * bump(self.wave_age / WAVE_TIME)

        cx, cy = x + w / 2, y + h / 2
        cy -= h * (0.03 * self.hover + 0.05 * lift)
        if self.shake_age is not None:
            cx += w * 0.07 * math.sin(self.shake_age * 44) * math.exp(-self.shake_age * 7)

        alpha = 1.0
        if self.deal_age < DEAL_DURATION:
            t = self.deal_age / DEAL_DURATION
            k = ease_out_back(t, 1.2)
            cx = lerp(self.deal_from[0], cx, k)
            cy = lerp(self.deal_from[1], cy, k)
            scale *= lerp(0.55, 1.0, ease_out_cubic(t))
            alpha = min(1.0, t * 5)

        cw, ch = max(1, int(w * scale * squash)), max(1, int(h * scale))
        full = (max(1, int(w * scale)), ch)
        elevated = 0.5 * self.hover + lift

        # Shadow, drifting further away as the card lifts.
        shadow = self.art.shadow((w, h))
        if (cw, ch) != (w, h):
            sw, sh = shadow.get_size()
            shadow = _fit(shadow, (max(1, int(sw * cw / w)), max(1, int(sh * ch / h))))
        gfx.blit_center(
            surface, shadow, (cx, cy + h * (0.035 + 0.06 * elevated)), alpha * (0.7 + 0.3 * min(1.0, elevated))
        )

        # Halos behind the card.
        if self.matched:
            glow = 0.22 + 0.78 * math.exp(-(self.match_age or 0.0) * 2.2)
            self._halo(surface, self.match_color, (cw, ch), (cx, cy), alpha * glow)
        elif self.hover > 0.02 and not self.face_up:
            self._halo(surface, Palette.LAVENDER, (cw, ch), (cx, cy), alpha * self.hover)
        elif self.face_up and not self.turning:
            self._halo(surface, Palette.LAVENDER, (cw, ch), (cx, cy), alpha * 0.6)
        if self.shake_age is not None:
            fade = 1 - self.shake_age / SHAKE_TIME
            self._halo(surface, Palette.DANGER, (cw, ch), (cx, cy), alpha * fade * 0.9)

        # The card itself.
        img = self.art.face(self.face, (w, h)) if front else self.art.back((w, h))
        if (cw, ch) != (w, h):
            img = pygame.transform.smoothscale(img, (cw, ch))
        if 0.0 < shown < 1.0:
            shade = int(255 * (0.5 + 0.5 * squash))
            img = img.copy() if img.get_size() == (w, h) else img
            img.fill((shade, shade, shade), special_flags=pygame.BLEND_RGB_MULT)
        left, top = round(cx - cw / 2), round(cy - ch / 2)
        gfx.blit_alpha(surface, img, (left, top), alpha)

        radius = card_radius(w)
        if self.shake_age is not None:  # a wrong guess: a rose rim that fades with the shake
            rim = gfx.rounded_outline((w, h), radius, Palette.DANGER, max(2.0, w / 50))
            gfx.blit_alpha(surface, _fit(rim, (cw, ch)), (left, top), alpha * (1 - self.shake_age / SHAKE_TIME))
        if self.hover > 0.02 and not self.face_up:
            rim = gfx.rounded_outline((w, h), radius, Palette.LAVENDER_DEEP, max(1.5, w / 80))
            gfx.blit_alpha(surface, _fit(rim, (cw, ch)), (left, top), alpha * self.hover * 0.9)
        if self.matched and front:
            if self.dim > 0.01:
                veil = _fit(gfx.rounded_rect((w, h), radius, (255, 255, 255, 70)), (cw, ch))
                gfx.blit_alpha(surface, veil, (left, top), alpha * self.dim)
            frame = gfx.rounded_outline((w, h), radius, self.match_color, max(2.0, w / 55))
            gfx.blit_alpha(surface, _fit(frame, (cw, ch)), (left, top), alpha)

        if self.focus > 0.02:
            pad = max(4, int(w * 0.05))
            ring = gfx.rounded_outline((w + pad * 2, h + pad * 2), radius + pad, Palette.FOCUS, max(2, w / 55))
            ring = _fit(ring, (max(1, int(full[0] + pad * 2 * scale)), int(ch + pad * 2 * scale)))
            gfx.blit_center(surface, ring, (cx, cy), alpha * self.focus)

    def _halo(self, surface, color, size, center, alpha) -> None:
        if alpha <= 0.01:
            return
        w, h = self.rect.size
        halo = self.art.halo((w, h), color)
        if size != (w, h):
            hw, hh = halo.get_size()
            halo = _fit(halo, (max(1, int(hw * size[0] / w)), max(1, int(hh * size[1] / h))))
        gfx.blit_center(surface, halo, center, alpha)
