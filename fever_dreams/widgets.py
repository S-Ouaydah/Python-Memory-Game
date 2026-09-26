"""Buttons, toggles, glass panels and keyboard focus handling."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import pygame

from . import gfx
from .config import Palette
from .tween import approach, lerp_color

if TYPE_CHECKING:
    from .app import App

GOLD_STOPS = ((0.0, Palette.GOLD_LIGHT), (0.55, Palette.GOLD), (1.0, Palette.GOLD_DEEP))


def nearest_in_direction(centers: Sequence[tuple[float, float]], current: int, dx: int, dy: int) -> int:
    """Index of the closest centre in direction (dx, dy), or ``current``."""
    cx, cy = centers[current]
    best, best_score = current, float("inf")
    for i, (x, y) in enumerate(centers):
        if i == current:
            continue
        ox, oy = x - cx, y - cy
        along = ox * dx + oy * dy
        if along <= 1:
            continue
        across = abs(ox * dy - oy * dx)
        score = along + across * 2.5
        if score < best_score:
            best, best_score = i, score
    return best


def frost(surface: pygame.Surface, rect: pygame.Rect, radius: int, alpha: float = 1.0) -> None:
    """Blur whatever is already drawn under ``rect`` (clipped to a rounded shape)."""
    clip = rect.clip(surface.get_rect())
    if clip.w < 8 or clip.h < 8:
        return
    small = pygame.transform.smoothscale(surface.subsurface(clip), (clip.w // 4, clip.h // 4))
    small = pygame.transform.box_blur(small, 5)
    blurred = pygame.transform.smoothscale(small, clip.size).convert_alpha()
    mask = gfx.rounded_rect(rect.size, radius, (255, 255, 255))
    blurred.blit(mask, (rect.x - clip.x, rect.y - clip.y), special_flags=pygame.BLEND_RGBA_MULT)
    gfx.blit_alpha(surface, blurred, clip.topleft, alpha)


def draw_panel(surface: pygame.Surface, rect: pygame.Rect, radius: int, alpha: float = 1.0, scale: float = 1.0) -> None:
    """A frosted-glass panel with a soft shadow."""
    size = (rect.w, rect.h)
    blur = max(8, int(28 * scale))
    shadow = gfx.soft_shadow(size, radius, blur, alpha=170, color=(4, 2, 10))
    gfx.blit_alpha(surface, shadow, (rect.x - 2 * blur, rect.y - 2 * blur + int(10 * scale)), alpha)
    frost(surface, rect, radius, alpha)
    body = gfx.rounded_rect(size, radius, (34, 20, 56, 196), 1, (255, 255, 255, 40))
    gfx.blit_alpha(surface, body, rect.topleft, alpha)
    sheen = gfx.rounded_gradient(size, radius, ((0.0, (255, 255, 255, 22)), (0.4, (255, 255, 255, 0))))
    gfx.blit_alpha(surface, sheen, rect.topleft, alpha)


class Widget:
    def __init__(self, app: App) -> None:
        self.app = app
        self.rect = pygame.Rect(0, 0, 0, 0)
        self.hover = 0.0
        self.focus = 0.0
        self.press = 0.0
        self.focused = False
        self.enabled = True
        self.visible = True
        self.hovered = False
        self._pressed_inside = False

    def contains(self, pos) -> bool:
        return self.visible and self.rect.collidepoint(pos)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not (self.visible and self.enabled):
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.contains(event.pos):
            self._pressed_inside = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self._pressed_inside
            self._pressed_inside = False
            if was and self.contains(event.pos):
                self.activate()
                return True
        return False

    def activate(self) -> None:
        pass

    def update(self, dt: float, mouse: tuple[int, int]) -> None:
        was = self.hovered
        self.hovered = self.enabled and self.contains(mouse)
        if self.hovered and not was:
            self.app.audio.play("hover", 0.6)
        if self.hovered:
            self.app.want_hand_cursor = True
        self.hover = approach(self.hover, 1.0 if self.hovered else 0.0, 14, dt)
        self.focus = approach(self.focus, 1.0 if self.focused and self.app.keyboard_mode else 0.0, 14, dt)
        pressing = self._pressed_inside and self.hovered
        self.press = approach(self.press, 1.0 if pressing else 0.0, 30, dt)

    def draw(self, surface: pygame.Surface, alpha: float = 1.0) -> None:
        raise NotImplementedError

    def draw_focus(self, surface: pygame.Surface, radius: int, alpha: float) -> None:
        if self.focus < 0.02:
            return
        s = self.app.ui
        pad = max(3, int(4 * s))
        ring = gfx.rounded_outline(
            (self.rect.w + pad * 2, self.rect.h + pad * 2), radius + pad, Palette.SKY, max(1.5, 2 * s)
        )
        gfx.blit_alpha(surface, ring, (self.rect.x - pad, self.rect.y - pad), self.focus * alpha)


class Button(Widget):
    """A pill button. Styles: ``primary`` (gold), ``glass``, ``icon`` (round)."""

    def __init__(
        self,
        app: App,
        label: str,
        on_click: Callable[[], None],
        *,
        style: str = "glass",
        icon: str | None = None,
        font_size: float = 17,
        badge: str | None = None,
    ) -> None:
        super().__init__(app)
        self.label = label
        self.on_click = on_click
        self.style = style
        self.icon = icon
        self.font_size = font_size
        self.badge = badge

    def activate(self) -> None:
        if self.enabled:
            self.app.audio.play("click")
            self.on_click()

    def draw(self, surface: pygame.Surface, alpha: float = 1.0) -> None:
        if not self.visible or alpha <= 0:
            return
        s = self.app.ui
        if not self.enabled:
            alpha *= 0.4
        w, h = self.rect.size
        radius = h // 2
        lift = int(round(2 * s * self.hover - 1 * s * self.press))
        x, y = self.rect.x, self.rect.y - lift

        if self.style == "primary":
            glow = gfx.soft_shadow((w, h), radius, max(6, int(h * 0.3)), alpha=150, color=Palette.GOLD)
            gfx.blit_center(surface, glow, (x + w / 2, y + h / 2 + 4 * s), alpha * (0.3 + 0.7 * self.hover))
            gfx.blit_alpha(surface, gfx.rounded_gradient((w, h), radius, GOLD_STOPS), (x, y), alpha)
            gfx.blit_alpha(
                surface, gfx.rounded_outline((w, h), radius, (255, 245, 220, 150), max(1.0, s)), (x, y), alpha
            )
            ink = Palette.INK_DARK
        else:
            base = gfx.rounded_rect((w, h), radius, (255, 255, 255, 16), 1, (255, 255, 255, 46))
            lit = gfx.rounded_rect((w, h), radius, (255, 255, 255, 34), 1, (*Palette.GOLD_LIGHT, 170))
            gfx.blit_alpha(surface, base, (x, y), alpha)
            gfx.blit_alpha(surface, lit, (x, y), alpha * self.hover)
            ink = lerp_color(Palette.INK_SOFT, Palette.INK, self.hover)

        font = self.app.fonts.get("semibold" if self.style == "primary" else "medium", self.font_size * s)
        label = gfx.text(font, self.label, ink) if self.label else None
        icon_size = int(h * 0.44)
        icon = gfx.icon(self.icon, icon_size, ink) if self.icon else None
        gap = int(9 * s) if (label and icon) else 0
        content_w = (label.get_width() if label else 0) + (icon_size if icon else 0) + gap
        cx = x + (w - content_w) // 2
        cy = y + h // 2
        if icon:
            gfx.blit_alpha(surface, icon, (cx, cy - icon_size // 2), alpha)
            cx += icon_size + gap
        if label:
            gfx.blit_alpha(surface, label, (cx, cy - label.get_height() // 2), alpha)
        if self.badge:
            self._draw_badge(surface, x + w, y, alpha)
        self.draw_focus(surface, radius, alpha)

    def _draw_badge(self, surface, right, top, alpha) -> None:
        s = self.app.ui
        font = self.app.fonts.get("semibold", 12 * s)
        label = gfx.text(font, self.badge, Palette.INK_DARK)
        d = max(int(20 * s), label.get_width() + int(10 * s))
        pill = gfx.rounded_rect((d, int(20 * s)), int(10 * s), Palette.ROSE)
        bx, by = right - d + int(6 * s), top - int(6 * s)
        gfx.blit_alpha(surface, pill, (bx, by), alpha)
        gfx.blit_center(surface, label, (bx + d / 2, by + 10 * s), alpha)


class Toggle(Widget):
    """A labelled on/off switch spanning a settings row."""

    def __init__(
        self, app: App, label: str, getter: Callable[[], bool], setter: Callable[[bool], None], description: str = ""
    ) -> None:
        super().__init__(app)
        self.label = label
        self.description = description
        self.getter = getter
        self.setter = setter
        self.knob = 1.0 if getter() else 0.0

    def activate(self) -> None:
        self.app.audio.play("click")
        self.setter(not self.getter())

    def update(self, dt: float, mouse) -> None:
        super().update(dt, mouse)
        self.knob = approach(self.knob, 1.0 if self.getter() else 0.0, 16, dt)

    def draw(self, surface: pygame.Surface, alpha: float = 1.0) -> None:
        s = self.app.ui
        x, y, w, h = self.rect
        radius = int(14 * s)
        row = gfx.rounded_rect((w, h), radius, (255, 255, 255, 14))
        gfx.blit_alpha(surface, row, (x, y), alpha * (0.4 + 0.6 * self.hover))

        pad = int(18 * s)
        title = gfx.text(self.app.fonts.get("medium", 17 * s), self.label, Palette.INK)
        if self.description:
            desc = gfx.text(self.app.fonts.get("regular", 13 * s), self.description, Palette.INK_MUTED)
            block = title.get_height() + desc.get_height()
            ty = y + (h - block) // 2
            gfx.blit_alpha(surface, title, (x + pad, ty), alpha)
            gfx.blit_alpha(surface, desc, (x + pad, ty + title.get_height()), alpha)
        else:
            gfx.blit_alpha(surface, title, (x + pad, y + (h - title.get_height()) // 2), alpha)

        tw, th = int(48 * s), int(28 * s)
        tx, tyy = x + w - pad - tw, y + (h - th) // 2
        off = gfx.rounded_rect((tw, th), th // 2, (255, 255, 255, 40), 1, (255, 255, 255, 50))
        on = gfx.rounded_gradient((tw, th), th // 2, GOLD_STOPS)
        gfx.blit_alpha(surface, off, (tx, tyy), alpha)
        gfx.blit_alpha(surface, on, (tx, tyy), alpha * self.knob)
        kd = th - int(6 * s)
        knob = gfx.circle(kd, (255, 255, 255))
        kx = tx + int(3 * s) + (tw - kd - int(6 * s)) * self.knob
        shadow = gfx.soft_shadow((kd, kd), kd // 2, max(2, int(3 * s)), alpha=110)
        gfx.blit_center(surface, shadow, (kx + kd / 2, tyy + th / 2 + s), alpha)
        gfx.blit_alpha(surface, knob, (kx, tyy + int(3 * s)), alpha)
        self.draw_focus(surface, radius, alpha)


class FocusGroup:
    """Keyboard navigation between widgets by screen position."""

    def __init__(self, widgets: Sequence[Widget] = ()) -> None:
        self.widgets = list(widgets)
        self.index = 0

    def set(self, widgets: Sequence[Widget], index: int = 0) -> None:
        self.widgets = list(widgets)
        self.index = max(0, min(index, len(self.widgets) - 1))
        self._sync()

    @property
    def current(self) -> Widget | None:
        return self.widgets[self.index] if self.widgets else None

    def focus(self, widget: Widget) -> None:
        if widget in self.widgets:
            self.index = self.widgets.index(widget)
            self._sync()

    def _sync(self) -> None:
        for i, w in enumerate(self.widgets):
            w.focused = i == self.index

    def handle_key(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.KEYDOWN or not self.widgets:
            return False
        live = [w for w in self.widgets if w.visible and w.enabled]
        if not live:
            return False
        if self.current not in live:
            self.index = self.widgets.index(live[0])
        key = event.key
        directions = {
            pygame.K_LEFT: (-1, 0),
            pygame.K_a: (-1, 0),
            pygame.K_RIGHT: (1, 0),
            pygame.K_d: (1, 0),
            pygame.K_UP: (0, -1),
            pygame.K_w: (0, -1),
            pygame.K_DOWN: (0, 1),
            pygame.K_s: (0, 1),
        }
        if key in directions:
            centers = [w.rect.center for w in live]
            pos = live.index(self.current)
            nxt = nearest_in_direction(centers, pos, *directions[key])
            self.index = self.widgets.index(live[nxt])
        elif key == pygame.K_TAB:
            pos = live.index(self.current)
            step = -1 if event.mod & pygame.KMOD_SHIFT else 1
            self.index = self.widgets.index(live[(pos + step) % len(live)])
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self._sync()
            self.current.activate()
            return True
        else:
            return False
        self._sync()
        return True
