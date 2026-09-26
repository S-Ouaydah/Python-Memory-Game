"""Title screen: pick a difficulty, read the rules, change settings."""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from typing import TYPE_CHECKING

import pygame

from .. import gfx
from ..config import CARD_ASPECT, DIFFICULTIES, Difficulty, Palette
from ..layout import compute_grid
from ..tween import approach, ease_out_cubic
from ..widgets import Button, FocusGroup, Toggle, Widget
from .base import Modal, Scene

if TYPE_CHECKING:
    from ..app import App

TITLE_STOPS = ((0.0, Palette.GOLD_LIGHT), (0.55, (255, 200, 190)), (1.0, Palette.ROSE))

HELP_ITEMS = (
    (
        "sparkle",
        "Find the twins",
        "Turn over two cards at a time. Matching dreamers stay revealed; the rest drift back.",
    ),
    ("star", "Build a combo", "Consecutive matches raise your multiplier, up to ×3 points per pair."),
    ("eye", "Glimpse", "Once per game, see every card for a moment. It costs 250 points."),
    ("trophy", "Chase your best", "Finish under par for a time bonus. Fewer moves earn more stars."),
)
CONTROLS = "Mouse or arrows + Space  ·  G glimpse  ·  R restart  ·  Esc pause  ·  F11 fullscreen"


def _reveal(age: float, delay: float, duration: float = 0.7) -> float:
    return ease_out_cubic((age - delay) / duration)


class DifficultyTile(Widget):
    def __init__(self, app: App, difficulty: Difficulty, number: int, on_click: Callable[[], None]) -> None:
        super().__init__(app)
        self.difficulty = difficulty
        self.number = number
        self.on_click = on_click
        grid = compute_grid(difficulty.pairs * 2, (0, 0, 1200, 620), CARD_ASPECT)
        self.grid = (grid.cols, grid.rows)

    def activate(self) -> None:
        self.app.audio.play("click")
        self.on_click()

    def draw(self, surface: pygame.Surface, alpha: float = 1.0) -> None:
        s = self.app.ui
        fonts = self.app.fonts
        w, h = self.rect.size
        lift = int(4 * s * self.hover - 2 * s * self.press)
        x, y = self.rect.x, self.rect.y - lift
        radius = int(20 * s)

        glow = gfx.soft_shadow((w, h), radius, max(6, int(18 * s)), alpha=120, color=Palette.GOLD)
        gfx.blit_center(surface, glow, (x + w / 2, y + h / 2 + 6 * s), alpha * self.hover * 0.55)
        base = gfx.rounded_rect((w, h), radius, (255, 255, 255, 14), 1, (255, 255, 255, 38))
        lit = gfx.rounded_rect((w, h), radius, (255, 255, 255, 28), 1, (*Palette.GOLD_LIGHT, 200))
        gfx.blit_alpha(surface, base, (x, y), alpha)
        gfx.blit_alpha(surface, lit, (x, y), alpha * self.hover)

        pad = int(20 * s)
        name = gfx.text(
            fonts.get("display", 36 * s), self.difficulty.name, Palette.GOLD_LIGHT if self.hover > 0.5 else Palette.INK
        )
        gfx.blit_alpha(surface, name, (x + pad, y + int(10 * s)), alpha)

        cards = self.difficulty.pairs * 2
        meta = gfx.text(
            fonts.get("regular", 14 * s), f"{self.difficulty.pairs} pairs · {cards} cards", Palette.INK_MUTED
        )
        my = y + int(10 * s) + name.get_height() - int(6 * s)
        gfx.blit_alpha(surface, meta, (x + pad, my), alpha)

        record = self.app.save.record(self.difficulty.key)
        ry = y + h - pad - int(14 * s)
        if record.wins:
            star_size = int(15 * s)
            for i in range(3):
                color = Palette.GOLD if i < record.best_stars else (255, 255, 255, 60)
                gfx.blit_alpha(
                    surface,
                    gfx.icon("star", star_size, color),
                    (x + pad + i * (star_size + int(2 * s)), ry - int(1 * s)),
                    alpha,
                )
            best = f"{record.best_score:,} pts · {gfx.format_time(record.best_time or 0)}"
            label = gfx.text(fonts.get("medium", 13 * s), best, Palette.INK_SOFT)
            gfx.blit_alpha(
                surface,
                label,
                (x + pad + 3 * (star_size + int(2 * s)) + int(6 * s), ry + (star_size - label.get_height()) // 2),
                alpha,
            )
        else:
            label = gfx.text(fonts.get("regular", 13 * s), "Not yet dreamt", Palette.INK_MUTED)
            gfx.blit_alpha(surface, label, (x + pad, ry), alpha)

        # Miniature of the board layout.
        cols, rows = self.grid
        dot_w, dot_h, gap = max(2, int(5 * s)), max(3, int(8 * s)), max(1, int(2 * s))
        gw = cols * dot_w + (cols - 1) * gap
        gx = x + w - pad - gw
        gy = y + pad
        color = Palette.GOLD_LIGHT if self.hover > 0.5 else (255, 255, 255, 70)
        dot = gfx.rounded_rect((dot_w, dot_h), max(1, int(1.5 * s)), color)
        for i in range(cards):
            r, c = divmod(i, cols)
            in_row = min(cols, cards - r * cols)
            ox = (cols - in_row) * (dot_w + gap) // 2
            gfx.blit_alpha(surface, dot, (gx + ox + c * (dot_w + gap), gy + r * (dot_h + gap)), alpha)

        key = gfx.text(fonts.get("medium", 12 * s), str(self.number), Palette.INK_FAINT)
        gfx.blit_alpha(
            surface,
            key,
            (x + w - pad - key.get_width(), y + h - pad - key.get_height()),
            alpha * (0.4 + 0.6 * self.app.keyboard_mode),
        )
        self.draw_focus(surface, radius, alpha)


class CardFan:
    """Five floating cards that occasionally turn over on their own."""

    ANGLES = (15, 7.5, 0, -7.5, -15)
    ORDER = (0, 4, 1, 3, 2)
    FLIP_TIME = 0.8

    def __init__(self, app: App, rng: random.Random) -> None:
        self.app = app
        self.rng = rng
        faces = rng.sample(range(app.art.count), 5)
        self.faces = faces
        self.up = [False, True, True, True, False]
        self.flip: list[float | None] = [None] * 5
        self.switched = [False] * 5
        self.timer = 2.2
        self.age = 0.0
        self.center = (0, 0)
        self.card_w = self.card_h = 1
        self._cache: dict = {}
        self.parallax = [0.0, 0.0]

    def layout(self, center: tuple[int, int], card_h: int) -> None:
        self.center = center
        self.card_h = max(2, int(card_h))
        self.card_w = max(2, int(card_h * CARD_ASPECT))
        self._cache.clear()
        self._glow = gfx.radial_glow(int(self.card_h * 2.4), (120, 50, 110)).convert()

    def _base(self, i: int) -> pygame.Surface:
        size = (self.card_w, self.card_h)
        return self.app.art.face(self.faces[i], size) if self.up[i] else self.app.art.back(size)

    def _rotated(self, i: int) -> tuple[pygame.Surface, pygame.Surface]:
        key = (i, self.up[i], self.faces[i])
        hit = self._cache.get(key)
        if hit is None:
            card = pygame.transform.rotozoom(self._base(i), self.ANGLES[i], 1.0)
            shadow = pygame.transform.rotozoom(self.app.art.shadow((self.card_w, self.card_h)), self.ANGLES[i], 1.0)
            hit = self._cache[key] = (card, shadow)
        return hit

    def update(self, dt: float, mouse: tuple[int, int]) -> None:
        self.age += dt
        self.timer -= dt
        if self.timer <= 0:
            idle = [i for i in range(5) if self.flip[i] is None]
            if idle:
                i = self.rng.choice(idle)
                self.flip[i] = 0.0
                self.switched[i] = False
            self.timer = self.rng.uniform(2.0, 3.4)
        for i in range(5):
            if self.flip[i] is None:
                continue
            self.flip[i] += dt / self.FLIP_TIME
            if self.flip[i] >= 0.5 and not self.switched[i]:
                self.switched[i] = True
                self.up[i] = not self.up[i]
                if self.up[i]:
                    choices = [f for f in range(self.app.art.count) if f not in self.faces]
                    self.faces[i] = self.rng.choice(choices)
            if self.flip[i] >= 1.0:
                self.flip[i] = None
        w, h = self.app.size
        tx = (mouse[0] - w / 2) / w * -18 * self.app.ui
        ty = (mouse[1] - h / 2) / h * -12 * self.app.ui
        self.parallax[0] = approach(self.parallax[0], tx, 4, dt)
        self.parallax[1] = approach(self.parallax[1], ty, 4, dt)

    def draw(self, surface: pygame.Surface, alpha: float) -> None:
        if alpha <= 0.01:
            return
        s = self.app.ui
        cx, cy = self.center
        glow = self._glow
        surface.blit(
            glow, (cx - glow.get_width() // 2, cy - glow.get_height() // 2), special_flags=pygame.BLEND_RGB_ADD
        )
        for i in self.ORDER:
            k = i - 2
            depth = 1.0 - abs(k) * 0.18
            x = cx + k * self.card_w * 0.5 + self.parallax[0] * depth
            y = (
                cy
                + abs(k) ** 1.6 * self.card_h * 0.045
                + math.sin(self.age * 0.9 + i * 1.3) * 7 * s
                + self.parallax[1] * depth
                + (1 - alpha) * 40 * s
            )
            flip = self.flip[i]
            card, shadow = self._rotated(i)
            if flip is not None:
                squash = abs(math.cos(math.pi * flip))
                lift = math.sin(math.pi * flip)
                base = self._base(i)
                scaled = pygame.transform.smoothscale(
                    base, (max(1, int(self.card_w * squash * (1 + 0.06 * lift))), int(self.card_h * (1 + 0.06 * lift)))
                )
                shade = int(255 * (0.55 + 0.45 * squash))
                scaled.fill((shade, shade, shade), special_flags=pygame.BLEND_RGB_MULT)
                card = pygame.transform.rotozoom(scaled, self.ANGLES[i], 1.0)
                y -= lift * 14 * s
            gfx.blit_center(surface, shadow, (x, y + 16 * s), alpha * 0.9)
            gfx.blit_center(surface, card, (x, y), alpha)


class HelpModal(Modal):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.ok = Button(app, "Got it", self.close, style="primary")
        self.set_widgets([self.ok])

    def layout(self, size: tuple[int, int]) -> None:
        s = self.app.ui
        w, h = int(620 * s), int(516 * s)
        self.panel = pygame.Rect((size[0] - w) // 2, (size[1] - h) // 2, w, h)
        bw, bh = int(180 * s), int(50 * s)
        self.ok.rect = pygame.Rect(self.panel.centerx - bw // 2, self.panel.bottom - bh - int(30 * s), bw, bh)

    def draw_content(self, surface, panel, alpha) -> None:
        s = self.app.ui
        fonts = self.app.fonts
        pad = int(40 * s)
        over = gfx.text(fonts.get("medium", 12 * s), "THE RULES OF THE DREAM", Palette.GOLD, tracking=3.5 * s)
        gfx.blit_alpha(surface, over, (panel.x + pad, panel.y + int(34 * s)), alpha)
        title = gfx.text(fonts.get("display", 46 * s), "How to play", Palette.INK)
        gfx.blit_alpha(surface, title, (panel.x + pad, panel.y + int(50 * s)), alpha)
        y = panel.y + int(122 * s)
        body_font = fonts.get("regular", 15 * s)
        text_x = panel.x + pad + int(52 * s)
        text_w = panel.w - (text_x - panel.x) - pad
        for icon_name, heading, body in HELP_ITEMS:
            bubble = gfx.circle(int(38 * s), (255, 255, 255, 22))
            gfx.blit_alpha(surface, bubble, (panel.x + pad, y), alpha)
            gfx.blit_center(
                surface,
                gfx.icon(icon_name, int(20 * s), Palette.GOLD_LIGHT),
                (panel.x + pad + 19 * s, y + 19 * s),
                alpha,
            )
            head = gfx.text(fonts.get("semibold", 17 * s), heading, Palette.INK)
            gfx.blit_alpha(surface, head, (text_x, y - int(1 * s)), alpha)
            ly = y + head.get_height()
            for line in gfx.wrap_lines(body_font, body, text_w):
                surf = gfx.text(body_font, line, Palette.INK_MUTED)
                gfx.blit_alpha(surface, surf, (text_x, ly), alpha)
                ly += surf.get_height()
            y = max(y + int(54 * s), ly + int(14 * s))
        controls = gfx.text(fonts.get("regular", 13 * s), CONTROLS, Palette.INK_FAINT)
        gfx.blit_center(surface, controls, (panel.centerx, self.ok.rect.y + self.offset - 26 * s), alpha)


class SettingsModal(Modal):
    def __init__(self, app: App) -> None:
        super().__init__(app)
        settings = app.save.settings
        self.toggles = [
            Toggle(app, "Sound effects", lambda: settings.sound, app.set_sound, "Chimes, flips and flourishes"),
            Toggle(
                app, "Ambient petals", lambda: settings.ambient, app.set_ambient, "Drifting blossoms and motes of light"
            ),
            Toggle(
                app, "Fullscreen", lambda: app.fullscreen, lambda _on: app.toggle_fullscreen(), "Also F11 or Alt+Enter"
            ),
        ]
        self.reset = Button(app, "Reset records", self._reset, icon="restart", font_size=15)
        self.done = Button(app, "Done", self.close, style="primary")
        self._confirm_age: float | None = None
        self.set_widgets([*self.toggles, self.reset, self.done], focus=0)

    def _reset(self) -> None:
        if self._confirm_age is None:
            self._confirm_age = 0.0
            self.reset.label = "Tap again to erase"
            return
        self.app.save.reset_records()
        self.app.save.save()
        self._confirm_age = None
        self.reset.label = "Records erased"
        self.reset.enabled = False

    def update(self, dt: float) -> None:
        super().update(dt)
        if self._confirm_age is not None:
            self._confirm_age += dt
            if self._confirm_age > 3.0:
                self._confirm_age = None
                self.reset.label = "Reset records"

    def layout(self, size: tuple[int, int]) -> None:
        s = self.app.ui
        w, h = int(500 * s), int(446 * s)
        self.panel = pygame.Rect((size[0] - w) // 2, (size[1] - h) // 2, w, h)
        pad = int(32 * s)
        y = self.panel.y + int(118 * s)
        for toggle in self.toggles:
            toggle.rect = pygame.Rect(self.panel.x + pad - int(14 * s), y, w - 2 * pad + int(28 * s), int(64 * s))
            y += int(70 * s)
        bh = int(48 * s)
        by = self.panel.bottom - bh - int(30 * s)
        self.reset.rect = pygame.Rect(self.panel.x + pad, by, int(200 * s), bh)
        self.done.rect = pygame.Rect(self.panel.right - pad - int(150 * s), by, int(150 * s), bh)

    def draw_content(self, surface, panel, alpha) -> None:
        s = self.app.ui
        fonts = self.app.fonts
        pad = int(32 * s)
        over = gfx.text(fonts.get("medium", 12 * s), "PREFERENCES", Palette.GOLD, tracking=3.5 * s)
        gfx.blit_alpha(surface, over, (panel.x + pad, panel.y + int(34 * s)), alpha)
        title = gfx.text(fonts.get("display", 46 * s), "Settings", Palette.INK)
        gfx.blit_alpha(surface, title, (panel.x + pad, panel.y + int(50 * s)), alpha)
        if self._confirm_age is not None:
            warn = gfx.text(fonts.get("regular", 13 * s), "This erases every best score.", Palette.DANGER)
            gfx.blit_alpha(surface, warn, (panel.x + pad, self.reset.rect.y + self.offset - int(24 * s)), alpha)


class MenuScene(Scene):
    def __init__(self, app: App, intro: bool = True) -> None:
        super().__init__(app)
        self.age = 0.0 if intro else 0.45
        self.tiles = [DifficultyTile(app, d, i + 1, lambda d=d: self.start(d)) for i, d in enumerate(DIFFICULTIES)]
        self.help_button = Button(app, "How to play", self.open_help, icon="book", font_size=15)
        self.settings_button = Button(app, "Settings", self.open_settings, icon="gear", font_size=15)
        self.quit_button = Button(app, "Quit", app.quit, icon="close", font_size=15)
        self.buttons = [self.help_button, self.settings_button, self.quit_button]
        self.focus = FocusGroup()
        last = app.save.settings.last_difficulty
        keys = [d.key for d in DIFFICULTIES]
        self.focus.set([*self.tiles, *self.buttons], keys.index(last) if last in keys else 0)
        self.fan = CardFan(app, random.Random(app.rng.random()))
        self.modal: Modal | None = None
        self.resize(app.size)

    # -- actions ----------------------------------------------------------------

    def start(self, difficulty: Difficulty) -> None:
        from .game import GameScene

        self.app.save.settings.last_difficulty = difficulty.key
        self.app.save.save()
        self.app.switch(lambda: GameScene(self.app, difficulty))

    def open_help(self) -> None:
        self._open(HelpModal(self.app))

    def open_settings(self) -> None:
        self._open(SettingsModal(self.app))

    def _open(self, modal: Modal) -> None:
        modal.layout(self.app.size)
        self.modal = modal

    # -- layout -------------------------------------------------------------------

    def resize(self, size: tuple[int, int]) -> None:
        w, h = size
        s = self.app.ui
        fonts = self.app.fonts
        self.left = int(w * 0.075)
        self.col_w = min(int(580 * s), int(w * 0.47))

        self.over = gfx.text(
            fonts.get("medium", 13 * s), "A MEMORY GAME OF DRIFTING BLOSSOMS", Palette.INK_MUTED, tracking=4 * s
        )
        title_px = 132 * s
        font = fonts.get("display", title_px)
        while font.size("Fever Dreams")[0] > self.col_w and title_px > 40:
            title_px -= 4
            font = fonts.get("display", title_px)
        self.title = gfx.gradient_text(font, "Fever Dreams", TITLE_STOPS)
        self.title_glow = gfx.glow(self.title, max(6, int(22 * s)), Palette.ROSE, strength=0.55)
        tag_font = fonts.get("display_medium", 25 * s)
        self.tagline = [
            gfx.text(tag_font, line, Palette.INK_SOFT)
            for line in ("Twenty-two dreamers wander the blossoms.", "Find each one’s twin before they drift away.")
        ]
        self.section = gfx.text(fonts.get("medium", 12 * s), "CHOOSE YOUR DREAM", Palette.GOLD, tracking=4 * s)

        block_h = (
            self.over.get_height()
            + self.title.get_height()
            + 2 * self.tagline[0].get_height()
            + int(40 * s)
            + self.section.get_height()
            + int(14 * s)
            + 2 * int(122 * s)
            + int(16 * s)
            + int(40 * s)
            + int(48 * s)
        )
        top = max(int(24 * s), (h - block_h) // 2)
        self.over_y = top
        self.title_y = self.over_y + self.over.get_height() - int(title_px * 0.08)
        self.tag_y = self.title_y + self.title.get_height() - int(title_px * 0.12)
        self.section_y = self.tag_y + 2 * self.tagline[0].get_height() + int(40 * s)
        tiles_y = self.section_y + self.section.get_height() + int(14 * s)
        gap = int(16 * s)
        tile_w, tile_h = (self.col_w - gap) // 2, int(122 * s)
        for i, tile in enumerate(self.tiles):
            r, c = divmod(i, 2)
            tile.rect = pygame.Rect(self.left + c * (tile_w + gap), tiles_y + r * (tile_h + gap), tile_w, tile_h)
        by = tiles_y + 2 * tile_h + gap + int(40 * s)
        bx = self.left
        for button, bw in zip(self.buttons, (170, 140, 110)):
            button.rect = pygame.Rect(bx, by, int(bw * s), int(46 * s))
            bx += int(bw * s) + int(12 * s)

        right = self.left + self.col_w
        space = w - right
        fan_h = min(h * 0.5, space * 0.78 / (CARD_ASPECT * 2.9))
        self.fan.layout((int(right + space * 0.5), int(h * 0.48)), int(fan_h))
        self.show_fan = fan_h > 120 * s * 0.6
        if self.modal:
            self.modal.layout(size)

    # -- loop -----------------------------------------------------------------------

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.modal:
            self.modal.handle_event(event)
            return
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN):
            self.age = max(self.age, 1.6)  # any input fast-forwards the intro
        for widget in (*self.tiles, *self.buttons):
            if widget.handle_event(event):
                self.focus.focus(widget)
                return
        if event.type == pygame.KEYDOWN:
            if pygame.K_1 <= event.key <= pygame.K_4:
                self.start(DIFFICULTIES[event.key - pygame.K_1])
                return
            if event.key == pygame.K_h:
                self.open_help()
                return
            self.focus.handle_key(event)

    def update(self, dt: float) -> None:
        self.age += dt
        interactive = self.modal is None and not self.app.transitioning
        mouse = pygame.mouse.get_pos() if interactive else (-1, -1)
        for widget in (*self.tiles, *self.buttons):
            widget.update(dt, mouse)
        self.fan.update(dt, pygame.mouse.get_pos())
        if self.modal:
            self.modal.update(dt)
            if self.modal.closed:
                self.modal = None

    def draw(self, surface: pygame.Surface) -> None:
        s = self.app.ui
        age = self.age
        if self.show_fan:
            self.fan.draw(surface, _reveal(age, 0.25, 1.0))

        a = _reveal(age, 0.05)
        gfx.blit_alpha(surface, self.over, (self.left, self.over_y + (1 - a) * 16 * s), a)
        a = _reveal(age, 0.12, 1.0)
        ty = self.title_y + (1 - a) * 22 * s
        pulse = 0.75 + 0.25 * math.sin(age * 1.4)
        pad = (self.title_glow.get_width() - self.title.get_width()) // 2
        gfx.blit_alpha(surface, self.title_glow, (self.left - pad, ty - pad), a * pulse)
        gfx.blit_alpha(surface, self.title, (self.left, ty), a)
        a = _reveal(age, 0.28)
        for i, line in enumerate(self.tagline):
            gfx.blit_alpha(surface, line, (self.left, self.tag_y + i * line.get_height() + (1 - a) * 16 * s), a)
        a = _reveal(age, 0.4)
        gfx.blit_alpha(surface, self.section, (self.left, self.section_y + (1 - a) * 12 * s), a)
        for i, tile in enumerate(self.tiles):
            a = _reveal(age, 0.45 + i * 0.07)
            offset = int((1 - a) * 26 * s)
            tile.rect.y += offset
            tile.draw(surface, a)
            tile.rect.y -= offset
        a = _reveal(age, 0.75)
        for button in self.buttons:
            button.draw(surface, a)

        foot = gfx.text(
            self.app.fonts.get("regular", 12 * s),
            "1–4 quick start  ·  F11 fullscreen  ·  F12 screenshot",
            Palette.INK_FAINT,
        )
        w, h = self.app.size
        gfx.blit_alpha(
            surface,
            foot,
            (w - foot.get_width() - int(24 * s), h - foot.get_height() - int(18 * s)),
            _reveal(age, 1.0) * 0.8,
        )
        if self.modal:
            self.modal.draw(surface)

    def focus_lost(self) -> None:
        pass
