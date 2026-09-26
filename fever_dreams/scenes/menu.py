"""Title screen: pick players and a difficulty, read the rules, change settings."""

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
from ..widgets import Button, Chip, FocusGroup, Toggle, Widget
from .base import Modal, Scene

if TYPE_CHECKING:
    from ..app import App

TITLE_STOPS = ((0.0, (228, 104, 158)), (0.5, (190, 106, 198)), (1.0, (118, 110, 216)))
MAX_PLAYERS = 4

HELP_ITEMS = (
    (
        "sparkle",
        "Find the twins",
        "Turn over two cards at a time. Matching dreamers stay revealed; the rest drift back.",
    ),
    ("star", "Build a combo", "Consecutive matches raise your multiplier, up to \u00d73 points per pair."),
    (
        "users",
        "Play together",
        "Up to four players take turns on one screen. A match earns another go; a miss passes the turn.",
    ),
    ("eye", "Glimpse", "Once per solo game, see every card for a moment. It costs 250 points."),
    ("trophy", "Chase your best", "Finish under par for a time bonus. Fewer moves earn more stars."),
)
CONTROLS = "Mouse or arrows + Space  \u00b7  G glimpse  \u00b7  R restart  \u00b7  Esc pause  \u00b7  F11 fullscreen"


def _reveal(age: float, delay: float, duration: float = 0.7) -> float:
    return ease_out_cubic((age - delay) / duration)


class DifficultyTile(Widget):
    def __init__(self, app: App, difficulty: Difficulty, on_click: Callable[[], None]) -> None:
        super().__init__(app)
        self.difficulty = difficulty
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

        glow = gfx.soft_shadow((w, h), radius, max(6, int(18 * s)), alpha=110, color=Palette.ROSE)
        gfx.blit_center(surface, glow, (x + w / 2, y + h / 2 + 6 * s), alpha * (0.25 + 0.75 * self.hover))
        base = gfx.rounded_rect((w, h), radius, Palette.GLASS, 1, Palette.GLASS_EDGE)
        lit = gfx.rounded_rect((w, h), radius, Palette.GLASS_HOVER, 1, (*Palette.ROSE_DEEP, 170))
        gfx.blit_alpha(surface, base, (x, y), alpha)
        gfx.blit_alpha(surface, lit, (x, y), alpha * self.hover)

        pad = int(18 * s)
        name_color = Palette.ACCENT if self.hover > 0.5 else Palette.INK
        name = gfx.text(fonts.get("display", 32 * s), self.difficulty.name, name_color)
        gfx.blit_alpha(surface, name, (x + pad, y + int(10 * s)), alpha)

        cards = self.difficulty.pairs * 2
        meta = gfx.text(
            fonts.get("regular", 13 * s), f"{self.difficulty.pairs} pairs \u00b7 {cards} cards", Palette.INK_MUTED
        )
        gfx.blit_alpha(surface, meta, (x + pad, y + int(10 * s) + name.get_height() - int(6 * s)), alpha)

        players = self.app.save.settings.players
        record = self.app.save.record(self.difficulty.key)
        ry = y + h - pad - int(14 * s)
        if players > 1:
            icon = gfx.icon("users", int(16 * s), Palette.INK_SOFT)
            gfx.blit_alpha(surface, icon, (x + pad, ry - int(1 * s)), alpha)
            label = gfx.text(fonts.get("medium", 13 * s), f"Hot-seat \u00b7 {players} players", Palette.INK_SOFT)
            gfx.blit_alpha(surface, label, (x + pad + int(22 * s), ry + (int(16 * s) - label.get_height()) // 2), alpha)
        elif record.wins:
            star_size = int(15 * s)
            for i in range(3):
                color = Palette.GOLD if i < record.best_stars else Palette.LINE
                gfx.blit_alpha(
                    surface,
                    gfx.icon("star", star_size, color),
                    (x + pad + i * (star_size + int(2 * s)), ry - int(1 * s)),
                    alpha,
                )
            best = f"{record.best_score:,} \u00b7 {gfx.format_time(record.best_time or 0)}"
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
        cols, _rows = self.grid
        dot_w, dot_h, gap = max(2, int(4 * s)), max(3, int(6 * s)), max(1, int(2 * s))
        gx = x + w - pad - (cols * dot_w + (cols - 1) * gap)
        gy = y + pad
        color = Palette.ROSE_DEEP if self.hover > 0.5 else (*Palette.LAVENDER_DEEP, 110)
        dot = gfx.rounded_rect((dot_w, dot_h), max(1, int(1.2 * s)), color)
        for i in range(cards):
            r, c = divmod(i, cols)
            in_row = min(cols, cards - r * cols)
            ox = (cols - in_row) * (dot_w + gap) // 2
            gfx.blit_alpha(surface, dot, (gx + ox + c * (dot_w + gap), gy + r * (dot_h + gap)), alpha)
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
        self._glow = gfx.soft_blob(int(self.card_h * 2.6), (255, 255, 255), 200).convert_alpha()

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
        gfx.blit_center(surface, glow, (cx, cy), alpha)
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
        w, h = int(640 * s), int(590 * s)
        self.panel = pygame.Rect((size[0] - w) // 2, (size[1] - h) // 2, w, h)
        bw, bh = int(180 * s), int(50 * s)
        self.ok.rect = pygame.Rect(self.panel.centerx - bw // 2, self.panel.bottom - bh - int(30 * s), bw, bh)

    def draw_content(self, surface, panel, alpha) -> None:
        s = self.app.ui
        fonts = self.app.fonts
        pad = int(40 * s)
        over = gfx.text(fonts.get("medium", 12 * s), "THE RULES OF THE DREAM", Palette.ACCENT, tracking=3.5 * s)
        gfx.blit_alpha(surface, over, (panel.x + pad, panel.y + int(34 * s)), alpha)
        title = gfx.text(fonts.get("display", 46 * s), "How to play", Palette.INK)
        gfx.blit_alpha(surface, title, (panel.x + pad, panel.y + int(50 * s)), alpha)
        y = panel.y + int(122 * s)
        body_font = fonts.get("regular", 15 * s)
        text_x = panel.x + pad + int(52 * s)
        text_w = panel.w - (text_x - panel.x) - pad
        for icon_name, heading, body in HELP_ITEMS:
            bubble = gfx.circle(int(38 * s), (255, 255, 255, 200))
            gfx.blit_alpha(surface, bubble, (panel.x + pad, y), alpha)
            gfx.blit_center(
                surface,
                gfx.icon(icon_name, int(20 * s), Palette.ACCENT),
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
        over = gfx.text(fonts.get("medium", 12 * s), "PREFERENCES", Palette.ACCENT, tracking=3.5 * s)
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
        self.chips = [
            Chip(
                app,
                "Solo" if n == 1 else str(n),
                lambda n=n: app.save.settings.players == n,
                lambda n=n: self.set_players(n),
            )
            for n in range(1, MAX_PLAYERS + 1)
        ]
        self.tiles = [DifficultyTile(app, d, lambda d=d: self.start(d)) for d in DIFFICULTIES]
        self.help_button = Button(app, "How to play", self.open_help, icon="book", font_size=15)
        self.settings_button = Button(app, "Settings", self.open_settings, icon="gear", font_size=15)
        self.quit_button = Button(app, "Quit", app.quit, icon="close", font_size=15)
        self.buttons = [self.help_button, self.settings_button, self.quit_button]
        self.widgets: list[Widget] = [*self.chips, *self.tiles, *self.buttons]
        self.focus = FocusGroup()
        last = app.save.settings.last_difficulty
        keys = [d.key for d in DIFFICULTIES]
        self.focus.set(self.widgets, len(self.chips) + (keys.index(last) if last in keys else 0))
        self.fan = CardFan(app, random.Random(app.rng.random()))
        self.modal: Modal | None = None
        self.resize(app.size)

    # -- actions ----------------------------------------------------------------

    def set_players(self, count: int) -> None:
        self.app.save.settings.players = count
        self.app.save.save()

    def start(self, difficulty: Difficulty) -> None:
        from .game import GameScene

        settings = self.app.save.settings
        settings.last_difficulty = difficulty.key
        self.app.save.save()
        self.app.switch(lambda: GameScene(self.app, difficulty, settings.players))

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
        self.left = int(w * 0.065)
        self.col_w = min(int(640 * s), int(w * 0.5))

        self.over = gfx.text(
            fonts.get("medium", 13 * s), "A MEMORY GAME OF DRIFTING BLOSSOMS", Palette.INK_MUTED, tracking=4 * s
        )
        title_px = 132 * s
        font = fonts.get("display", title_px)
        while font.size("Fever Dreams")[0] > self.col_w and title_px > 40:
            title_px -= 4
            font = fonts.get("display", title_px)
        self.title = gfx.gradient_text(font, "Fever Dreams", TITLE_STOPS)
        self.title_glow = gfx.glow(self.title, max(6, int(20 * s)), (255, 255, 255), strength=1.6)
        tag_font = fonts.get("display_medium", 25 * s)
        self.tagline = [
            gfx.text(tag_font, line, Palette.INK_SOFT)
            for line in (
                "Twenty-two dreamers wander the blossoms.",
                "Find each one\u2019s twin before they drift away.",
            )
        ]
        self.section = gfx.text(fonts.get("medium", 12 * s), "CHOOSE YOUR DREAM", Palette.ACCENT, tracking=4 * s)
        self.players_label = gfx.text(fonts.get("medium", 12 * s), "PLAYERS", Palette.INK_MUTED, tracking=3 * s)

        gap = int(14 * s)
        tile_h = int(112 * s)
        chip_h = int(30 * s)
        block_h = (
            self.over.get_height()
            + self.title.get_height()
            + 2 * self.tagline[0].get_height()
            + int(36 * s)
            + chip_h
            + int(14 * s)
            + 2 * tile_h
            + gap
            + int(36 * s)
            + int(46 * s)
        )
        top = max(int(20 * s), (h - block_h) // 2)
        self.over_y = top
        self.title_y = self.over_y + self.over.get_height() - int(title_px * 0.08)
        self.tag_y = self.title_y + self.title.get_height() - int(title_px * 0.12)
        row_y = self.tag_y + 2 * self.tagline[0].get_height() + int(36 * s)
        self.section_y = row_y + (chip_h - self.section.get_height()) // 2

        # Player chips, right-aligned on the section row.
        widths = [int(62 * s)] + [int(40 * s)] * (MAX_PLAYERS - 1)
        cx = self.left + self.col_w - (sum(widths) + int(6 * s) * (len(widths) - 1))
        self.players_label_pos = (
            cx - self.players_label.get_width() - int(12 * s),
            row_y + (chip_h - self.players_label.get_height()) // 2,
        )
        for chip, cw in zip(self.chips, widths):
            chip.rect = pygame.Rect(cx, row_y, cw, chip_h)
            cx += cw + int(6 * s)

        # Difficulty tiles: three on top, two wider ones below.
        tiles_y = row_y + chip_h + int(14 * s)
        top_w = (self.col_w - 2 * gap) // 3
        bottom_w = (self.col_w - gap) // 2
        for i, tile in enumerate(self.tiles):
            if i < 3:
                tile.rect = pygame.Rect(self.left + i * (top_w + gap), tiles_y, top_w, tile_h)
            else:
                j = i - 3
                tile.rect = pygame.Rect(self.left + j * (bottom_w + gap), tiles_y + tile_h + gap, bottom_w, tile_h)

        by = tiles_y + 2 * tile_h + gap + int(36 * s)
        bx = self.left
        for button, bw in zip(self.buttons, (170, 140, 110)):
            button.rect = pygame.Rect(bx, by, int(bw * s), int(46 * s))
            bx += int(bw * s) + int(12 * s)

        right = self.left + self.col_w
        space = w - right
        fan_h = min(h * 0.5, space * 0.8 / (CARD_ASPECT * 2.7))
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
        for widget in self.widgets:
            if widget.handle_event(event):
                self.focus.focus(widget)
                return
        if event.type == pygame.KEYDOWN:
            if pygame.K_1 <= event.key < pygame.K_1 + len(DIFFICULTIES):
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
        for widget in self.widgets:
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
        pulse = 0.8 + 0.2 * math.sin(age * 1.4)
        pad = (self.title_glow.get_width() - self.title.get_width()) // 2
        gfx.blit_alpha(surface, self.title_glow, (self.left - pad, ty - pad), a * pulse)
        gfx.blit_alpha(surface, self.title, (self.left, ty), a)
        a = _reveal(age, 0.28)
        for i, line in enumerate(self.tagline):
            gfx.blit_alpha(surface, line, (self.left, self.tag_y + i * line.get_height() + (1 - a) * 16 * s), a)
        a = _reveal(age, 0.4)
        gfx.blit_alpha(surface, self.section, (self.left, self.section_y + (1 - a) * 12 * s), a)
        gfx.blit_alpha(surface, self.players_label, self.players_label_pos, a)
        for chip in self.chips:
            chip.draw(surface, a)
        for i, tile in enumerate(self.tiles):
            a = _reveal(age, 0.45 + i * 0.06)
            offset = int((1 - a) * 26 * s)
            tile.rect.y += offset
            tile.draw(surface, a)
            tile.rect.y -= offset
        a = _reveal(age, 0.75)
        for button in self.buttons:
            button.draw(surface, a)

        foot = gfx.text(
            self.app.fonts.get("regular", 12 * s),
            f"1\u2013{len(DIFFICULTIES)} quick start  \u00b7  F11 fullscreen  \u00b7  F12 screenshot",
            Palette.INK_FAINT,
        )
        w, h = self.app.size
        gfx.blit_alpha(
            surface,
            foot,
            (w - foot.get_width() - int(24 * s), h - foot.get_height() - int(18 * s)),
            _reveal(age, 1.0) * 0.9,
        )
        if self.modal:
            self.modal.draw(surface)
