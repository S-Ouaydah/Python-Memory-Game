"""The board: dealing, flipping, scoring, pausing and the results screen."""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from enum import Enum, auto
from functools import lru_cache
from typing import TYPE_CHECKING

import pygame

from .. import gfx
from ..cards import CardSprite
from ..config import (
    CARD_ASPECT,
    DEAL_STAGGER,
    FLIP_DURATION,
    GLIMPSE_DURATION,
    MISMATCH_DELAY,
    WIN_CELEBRATION,
    Difficulty,
    Palette,
    next_difficulty,
)
from ..layout import compute_grid
from ..logic import GLIMPSE_COST, CardState, FinalScore, MemoryGame, Outcome, streak_multiplier
from ..particles import Effects
from ..storage import NewBests
from ..tween import approach, bump, ease_out_back, ease_out_cubic, lerp_color
from ..widgets import HONEY_STOPS, Button, draw_panel, nearest_in_direction
from .base import Modal, Scene

if TYPE_CHECKING:
    from ..app import App

DIRECTIONS = {
    pygame.K_LEFT: (-1, 0),
    pygame.K_a: (-1, 0),
    pygame.K_RIGHT: (1, 0),
    pygame.K_d: (1, 0),
    pygame.K_UP: (0, -1),
    pygame.K_w: (0, -1),
    pygame.K_DOWN: (0, 1),
    pygame.K_s: (0, 1),
}
ACTIVATE = (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER)


@lru_cache(maxsize=8)
def _star_glow(size: int, radius: int) -> pygame.Surface:
    return gfx.glow(gfx.icon("star", size, Palette.GOLD), radius, Palette.GOLD, strength=0.9)


class Phase(Enum):
    DEALING = auto()
    PLAYING = auto()
    GLIMPSE = auto()
    CELEBRATING = auto()
    RESULTS = auto()


class GameScene(Scene):
    def __init__(self, app: App, difficulty: Difficulty, players: int = 1) -> None:
        super().__init__(app)
        self.difficulty = difficulty
        self.players = players
        self.multiplayer = players > 1
        self.effects = Effects()
        self.top_effects = Effects()  # drawn above dialogs
        self.pause_button = Button(app, "", self.pause, icon="pause")
        self.glimpse_button = Button(app, "Glimpse", self.glimpse, icon="eye", font_size=15)
        self.restart_button = Button(app, "", self.restart, icon="restart")
        self.hud_buttons = [self.pause_button, self.glimpse_button, self.restart_button]
        self.modal: Modal | None = None

        rng = app.rng
        faces = rng.sample(range(app.art.face_pool(difficulty.pairs)), difficulty.pairs)
        self.game = MemoryGame(
            faces, rng=random.Random(rng.random()), glimpses=0 if self.multiplayer else 1, players=players
        )
        self.glimpse_button.visible = not self.multiplayer
        self.turn_glow = [1.0 if i == 0 else 0.0 for i in range(players)]
        self.banner_player: int | None = None
        self.banner_age = 0.0
        self.sprites = [CardSprite(i, card.face, app.art) for i, card in enumerate(self.game.cards)]
        self.phase = Phase.DEALING
        self.elapsed = 0.0
        self.clock_running = False
        self.mismatch_timer: float | None = None
        self.glimpse_timer = 0.0
        self.celebrate_timer = 0.0
        self.scheduled: list[list] = []
        self.hover_index: int | None = None
        self.focus_index: int | None = None
        self.display_score = 0.0
        self.progress = 0.0
        self.combo_shown = 0.0
        self.combo_age = 0.0
        self.age = 0.0
        self.final: FinalScore | None = None
        self.new_bests = NewBests()
        self.first_clear = False
        self.layout(app.size)

    # -- lifecycle ----------------------------------------------------------------

    def enter(self) -> None:
        w, h = self.app.size
        stagger = min(DEAL_STAGGER, 1.1 / len(self.sprites))
        origin = (w / 2, h + self.grid.card_h)
        for i, sprite in enumerate(self.sprites):
            sprite.deal(origin, 0.15 + i * stagger)
        self.app.audio.play("deal", 0.8)
        if self.multiplayer:
            self.later(0.2 + len(self.sprites) * stagger + 0.5, lambda: self.show_turn(0))
            if not getattr(self.app, "hotseat_hint_shown", False):
                self.app.hotseat_hint_shown = True
                self.app.toast("Take turns: a match earns another go, a miss passes the turn")
        elif not any(r.wins for r in self.app.save.records.values()):
            self.app.toast("Turn over two cards at a time to find each dreamer\u2019s twin")

    def focus_lost(self) -> None:
        if self.clock_running and self.phase in (Phase.PLAYING, Phase.GLIMPSE) and self.modal is None:
            self.pause()

    def resize(self, size: tuple[int, int]) -> None:
        self.layout(size)
        if self.modal:
            self.modal.layout(size)

    def layout(self, size: tuple[int, int]) -> None:
        w, h = size
        s = self.app.ui
        margin = int(20 * s)
        self.hud = pygame.Rect(margin, margin, w - 2 * margin, int(78 * s))
        self.footer_h = int(36 * s)
        top = self.hud.bottom + int(30 * s)
        area = (int(40 * s), top, w - int(80 * s), h - top - self.footer_h - int(12 * s))
        self.grid = compute_grid(len(self.sprites), area, CARD_ASPECT, 0.1, max_card_w=250 * s)
        for sprite, rect in zip(self.sprites, self.grid.rects):
            sprite.rect = pygame.Rect(rect)

        d = int(46 * s)
        cy = self.hud.centery - d // 2
        self.pause_button.rect = pygame.Rect(self.hud.x + int(16 * s), cy, d, d)
        self.restart_button.rect = pygame.Rect(self.hud.right - int(16 * s) - d, cy, d, d)
        gw = int(146 * s)
        self.glimpse_button.rect = pygame.Rect(self.restart_button.rect.x - int(10 * s) - gw, cy, gw, d)

    # -- actions --------------------------------------------------------------------

    def later(self, delay: float, action: Callable[[], None]) -> None:
        self.scheduled.append([delay, action])

    def pause(self) -> None:
        if self.modal is None and self.phase not in (Phase.CELEBRATING, Phase.RESULTS):
            self.open(PauseModal(self))

    def open(self, modal: Modal) -> None:
        modal.layout(self.app.size)
        self.modal = modal

    def restart(self) -> None:
        self.app.switch(lambda: GameScene(self.app, self.difficulty, self.players))

    def play(self, difficulty: Difficulty) -> None:
        self.app.save.settings.last_difficulty = difficulty.key
        self.app.save.save()
        self.app.switch(lambda: GameScene(self.app, difficulty, self.players))

    def to_menu(self) -> None:
        from .menu import MenuScene

        self.app.switch(lambda: MenuScene(self.app, intro=False))

    def skip_deal(self) -> None:
        for sprite in self.sprites:
            sprite.finish_deal()
        self.phase = Phase.PLAYING

    def glimpse(self) -> None:
        if self.phase is not Phase.PLAYING:
            return
        if not self.game.use_glimpse():
            self.glimpse_button.enabled = False
            return
        self.clock_running = True
        self._turn_down(self.game.resolve_mismatch())
        self.phase = Phase.GLIMPSE
        self.glimpse_timer = GLIMPSE_DURATION
        for i, card in enumerate(self.game.cards):
            if card.state is CardState.HIDDEN:
                self.sprites[i].turn(True, speed=1.4)
        self.glimpse_button.enabled = False
        self.glimpse_button.badge = None
        self.app.audio.play("glimpse")
        self.effects.text(
            self._popup(f"−{GLIMPSE_COST}", Palette.DANGER),
            self.hud.centerx,
            self.hud.bottom + 30 * self.app.ui,
            life=1.2,
            rise=24 * self.app.ui,
        )

    def _turn_down(self, indices) -> None:
        for i in indices:
            self.sprites[i].turn(False)
        if indices:
            self.mismatch_timer = None

    def select(self, index: int) -> None:
        if self.phase is not Phase.PLAYING:
            return
        result = self.game.flip(index)
        self._turn_down(result.hidden)
        if result.outcome is Outcome.IGNORED:
            return
        self.clock_running = True
        self.sprites[index].turn(True)
        self.app.audio.play("flip", 0.9)
        if result.outcome is Outcome.MATCH:
            self.later(FLIP_DURATION * 0.85, lambda r=result: self._on_match(r))
        elif result.outcome is Outcome.MISMATCH:
            self.mismatch_timer = MISMATCH_DELAY
            self.later(FLIP_DURATION * 0.9, lambda r=result: self._on_mismatch(r))
            if self.multiplayer:
                self.later(FLIP_DURATION * 1.2, lambda p=result.next_player: self.show_turn(p))

    def player_color(self, player: int) -> tuple[int, int, int]:
        return Palette.PLAYERS[player % len(Palette.PLAYERS)]

    def show_turn(self, player: int) -> None:
        if self.phase in (Phase.CELEBRATING, Phase.RESULTS):
            return
        self.banner_player = player
        self.banner_age = 0.0

    def _on_match(self, result) -> None:
        s = self.app.ui
        a, b = self.sprites[result.index], self.sprites[result.partner]
        color = self.player_color(result.player) if self.multiplayer else Palette.GOLD
        colors = (color, Palette.GOLD, Palette.ROSE_DEEP) if self.multiplayer else None
        for sprite in (a, b):
            sprite.mark_matched(color)
            cx, cy = sprite.rect.center
            if colors:
                self.effects.sparkles(cx, cy, 14 + 2 * min(result.streak, 6), 260 * s, colors=colors, scale=s)
            else:
                self.effects.sparkles(cx, cy, 14 + 2 * min(result.streak, 6), 260 * s, scale=s)
            self.effects.ring(cx, cy, sprite.rect.h * 0.75, color)
        self.app.audio.play_match(result.streak)
        self.app.background.flash = min(1.0, 0.35 + 0.12 * result.streak)
        mx = (a.rect.centerx + b.rect.centerx) / 2
        my = min(a.rect.top, b.rect.top) + a.rect.h * 0.35
        popup_color = color if self.multiplayer else Palette.GOLD_DEEP
        self.effects.text(self._popup(f"+{result.points}", popup_color), mx, my, rise=56 * s)
        if result.streak >= 2:
            self.combo_age = 0.0
        if result.finished:
            self._on_win()

    def _on_mismatch(self, result) -> None:
        if self.game.pending != (result.partner, result.index):
            return  # the player already moved on
        for i in self.game.pending:
            self.sprites[i].shake()
        self.app.audio.play("miss", 0.8)

    def _on_win(self) -> None:
        self.phase = Phase.CELEBRATING
        self.clock_running = False
        self.celebrate_timer = WIN_CELEBRATION
        self.banner_player = None
        self.final = self.game.final_score(self.elapsed, self.difficulty.par_time)
        if not self.multiplayer:  # records are for solo play
            save = self.app.save
            self.new_bests = save.register_win(
                self.difficulty.key, self.final.total, self.elapsed, self.game.moves, self.final.stars
            )
            self.first_clear = save.record(self.difficulty.key).wins == 1
            save.save()
        w, h = self.app.size
        cx, cy = w / 2, h / 2
        for sprite in self.sprites:
            dist = math.hypot(sprite.rect.centerx - cx, sprite.rect.centery - cy) / max(w, h)
            sprite.wave(0.1 + dist * 0.9)
        self.later(0.15, lambda: self.app.audio.play("win"))
        s = self.app.ui
        self.effects.petal_burst(0, h, 70, 900 * s, spread=0.8, direction=-math.pi / 3)
        self.effects.petal_burst(w, h, 70, 900 * s, spread=0.8, direction=-2 * math.pi / 3)

    def _popup(self, label: str, color) -> pygame.Surface:
        s = self.app.ui
        text = gfx.text(self.app.fonts.get("semibold", 32 * s), label, color)
        # A white halo keeps the number readable over busy card art.
        dark_r, glow_r = max(4, int(9 * s)), max(2, int(4 * s))
        out = gfx.glow(text, dark_r, (255, 255, 255), strength=3.0)
        pad = 2 * dark_r
        out.blit(gfx.glow(text, glow_r, color, strength=0.6), (pad - 2 * glow_r, pad - 2 * glow_r))
        out.blit(text, (pad, pad))
        return out

    # -- input ----------------------------------------------------------------------

    def card_at(self, pos) -> int | None:
        for sprite in self.sprites:
            if sprite.rect.collidepoint(pos):
                return sprite.index
        return None

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.modal:
            self.modal.handle_event(event)
            return
        for button in self.hud_buttons:
            if button.handle_event(event):
                return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.phase is Phase.DEALING:
                self.skip_deal()
                return
            index = self.card_at(event.pos)
            if index is not None:
                self.select(index)
            elif self.game.pending and self.phase is Phase.PLAYING:
                self._turn_down(self.game.resolve_mismatch())
        elif event.type == pygame.KEYDOWN:
            self._handle_key(event)

    def _handle_key(self, event: pygame.event.Event) -> None:
        key = event.key
        if key in (pygame.K_ESCAPE, pygame.K_p):
            self.pause()
        elif key == pygame.K_g:
            self.glimpse()
        elif key == pygame.K_r:
            self.restart()
        elif self.phase is Phase.DEALING:
            self.skip_deal()
        elif key in DIRECTIONS:
            if self.focus_index is None:
                self.focus_index = self.hover_index if self.hover_index is not None else 0
            else:
                centers = [s.rect.center for s in self.sprites]
                self.focus_index = nearest_in_direction(centers, self.focus_index, *DIRECTIONS[key])
        elif key in ACTIVATE:
            if self.focus_index is None:
                self.focus_index = 0
            else:
                self.select(self.focus_index)

    # -- update ---------------------------------------------------------------------

    def update(self, dt: float) -> None:
        self.age += dt
        paused = self.modal is not None and isinstance(self.modal, PauseModal)
        if not paused:
            self._update_game(dt)

        interactive = self.modal is None and not self.app.transitioning
        mouse = pygame.mouse.get_pos() if interactive else (-1, -1)
        for button in self.hud_buttons:
            button.update(dt, mouse)

        self.hover_index = None
        if interactive and self.phase is Phase.PLAYING:
            index = self.card_at(mouse)
            if index is not None and self.game.is_selectable(index):
                self.hover_index = index
                self.app.want_hand_cursor = True
        show_focus = self.app.keyboard_mode and self.modal is None and self.phase is Phase.PLAYING
        for sprite in self.sprites:
            sprite.update(dt, sprite.index == self.hover_index, show_focus and sprite.index == self.focus_index)

        self.effects.update(dt)
        self.top_effects.update(dt)
        self.display_score = approach(self.display_score, self.game.score, 9, dt)
        self.progress = approach(self.progress, self.game.matches / self.game.pairs, 6, dt)
        self.combo_age += dt
        self.banner_age += dt
        for i in range(self.players):
            self.turn_glow[i] = approach(self.turn_glow[i], 1.0 if i == self.game.current else 0.0, 10, dt)
        self.combo_shown = approach(self.combo_shown, 1.0 if self.game.streak >= 2 else 0.0, 10, dt)
        self.glimpse_button.enabled = self.game.glimpses_left > 0 and self.phase is Phase.PLAYING
        self.glimpse_button.badge = str(self.game.glimpses_left) if self.game.glimpses_left else None

        if self.modal:
            self.modal.update(dt)
            if self.modal.closed:
                self.modal = None

    def _update_game(self, dt: float) -> None:
        if self.clock_running and self.phase in (Phase.PLAYING, Phase.GLIMPSE):
            self.elapsed += dt
        for item in list(self.scheduled):
            item[0] -= dt
            if item[0] <= 0:
                self.scheduled.remove(item)
                item[1]()

        if self.phase is Phase.DEALING and not any(s.dealing for s in self.sprites):
            self.phase = Phase.PLAYING
        elif self.phase is Phase.PLAYING and self.mismatch_timer is not None:
            self.mismatch_timer -= dt
            if self.mismatch_timer <= 0:
                self.mismatch_timer = None
                self._turn_down(self.game.resolve_mismatch())
        elif self.phase is Phase.GLIMPSE:
            self.glimpse_timer -= dt
            if self.glimpse_timer <= 0:
                for i, card in enumerate(self.game.cards):
                    if card.state is CardState.HIDDEN:
                        self.sprites[i].turn(False, speed=1.2)
                self.phase = Phase.PLAYING
        elif self.phase is Phase.CELEBRATING:
            self.celebrate_timer -= dt
            if self.celebrate_timer <= 0:
                self.phase = Phase.RESULTS
                self.open(ResultsModal(self))

    # -- drawing --------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        def elevation(sprite: CardSprite) -> float:
            return (
                sprite.hover
                + (1.0 if sprite.turning else 0.0)
                + (sprite.wave_age is not None)
                + (sprite.match_age is not None and sprite.match_age < 0.6)
                + (sprite.shake_age is not None)
                + sprite.focus
            )

        for sprite in sorted(self.sprites, key=elevation):
            sprite.draw(surface)
        self.effects.draw(surface)
        self._draw_banner(surface)
        self._draw_hud(surface)
        self._draw_combo(surface)
        self._draw_footer(surface)
        if self.modal:
            self.modal.draw(surface)
        self.top_effects.draw(surface)

    def _draw_hud(self, surface: pygame.Surface) -> None:
        s = self.app.ui
        fonts = self.app.fonts
        hud = self.hud
        radius = int(24 * s)
        intro = ease_out_cubic(self.age / 0.6)
        offset = int((1 - intro) * -30 * s)
        hud = hud.move(0, offset)
        draw_panel(surface, hud, radius, intro, s)

        # Difficulty name and progress.
        nx = self.pause_button.rect.right + int(16 * s)
        name = gfx.text(fonts.get("display", 30 * s), self.difficulty.name, Palette.INK)
        gfx.blit_alpha(surface, name, (nx, hud.y + int(10 * s)), intro)
        record = self.app.save.record(self.difficulty.key)
        if self.multiplayer:
            sub = f"{gfx.format_time(self.elapsed)}  \u00b7  {self.game.moves} moves"
        elif record.best_score is not None:
            sub = f"Best {record.best_score:,}"
        else:
            sub = self.difficulty.tagline
        sub_surf = gfx.text(fonts.get("regular", 13 * s), sub, Palette.INK_MUTED)
        gfx.blit_alpha(surface, sub_surf, (nx, hud.y + int(10 * s) + name.get_height() - int(6 * s)), intro)

        if self.multiplayer:
            self._draw_players(surface, hud, intro)
        else:
            self._draw_stats(surface, hud, intro)
        self._draw_rail(surface, hud, radius, intro)

        for button in self.hud_buttons:
            button.rect.y += offset
            button.draw(surface, intro)
            button.rect.y -= offset

    def _draw_stats(self, surface: pygame.Surface, hud: pygame.Rect, intro: float) -> None:
        s = self.app.ui
        fonts = self.app.fonts
        stats = (
            ("TIME", gfx.format_time(self.elapsed), Palette.INK),
            ("MOVES", str(self.game.moves), Palette.INK),
            ("PAIRS", f"{self.game.matches}/{self.game.pairs}", Palette.INK),
            ("SCORE", f"{int(round(self.display_score)):,}", Palette.ACCENT),
        )
        block = int(118 * s)
        left = hud.centerx - block * len(stats) // 2
        label_font = fonts.get("medium", 11 * s)
        value_font = fonts.get("semibold", 25 * s)
        for i, (label, value, color) in enumerate(stats):
            cx = left + block * i + block // 2
            lab = gfx.text(label_font, label, Palette.INK_FAINT, tracking=2.5 * s)
            val = gfx.text(value_font, value, color)
            gfx.blit_alpha(surface, lab, (cx - lab.get_width() // 2, hud.y + int(15 * s)), intro)
            gfx.blit_alpha(surface, val, (cx - val.get_width() // 2, hud.y + int(29 * s)), intro)
            if i:
                sep = gfx.rounded_rect((max(1, int(s)), int(34 * s)), 0, Palette.LINE)
                gfx.blit_alpha(surface, sep, (left + block * i, hud.y + int(22 * s)), intro)

    def _draw_players(self, surface: pygame.Surface, hud: pygame.Rect, intro: float) -> None:
        """One chip per player; the one whose turn it is lights up in their colour."""
        s = self.app.ui
        fonts = self.app.fonts
        cw, ch, gap = int(138 * s), int(52 * s), int(10 * s)
        total = self.players * cw + (self.players - 1) * gap
        x = hud.centerx - total // 2
        y = hud.centery - ch // 2 - int(2 * s)
        radius = int(16 * s)
        for i in range(self.players):
            color = self.player_color(i)
            glow = self.turn_glow[i]
            rect = pygame.Rect(x + i * (cw + gap), y, cw, ch)
            halo = gfx.soft_shadow((cw, ch), radius, max(4, int(10 * s)), 160, color)
            gfx.blit_center(surface, halo, rect.center, intro * glow * 0.8)
            base = gfx.rounded_rect((cw, ch), radius, Palette.GLASS, 1, Palette.LINE)
            lit = gfx.rounded_rect(
                (cw, ch), radius, lerp_color(color, (255, 255, 255), 0.72) + (255,), max(2, int(2 * s)), color
            )
            gfx.blit_alpha(surface, base, rect.topleft, intro)
            gfx.blit_alpha(surface, lit, rect.topleft, intro * glow)
            dot = gfx.circle(int(12 * s), color)
            gfx.blit_center(surface, dot, (rect.x + 20 * s, rect.centery), intro)
            name = gfx.text(fonts.get("medium", 12 * s), f"Player {i + 1}", Palette.INK_MUTED)
            pairs = self.game.player_pairs[i]
            value = gfx.text(fonts.get("semibold", 19 * s), f"{pairs} pair{'s' if pairs != 1 else ''}", Palette.INK)
            tx = rect.x + int(34 * s)
            block = name.get_height() + value.get_height() - int(4 * s)
            ty = rect.centery - block // 2
            gfx.blit_alpha(surface, name, (tx, ty), intro)
            gfx.blit_alpha(surface, value, (tx, ty + name.get_height() - int(4 * s)), intro)

    def _draw_rail(self, surface: pygame.Surface, hud: pygame.Rect, radius: int, intro: float) -> None:
        s = self.app.ui
        rail_w = hud.w - 2 * radius
        rail_h = max(2, int(3 * s))
        rx, ry = hud.x + radius, hud.bottom - rail_h - int(6 * s)
        gfx.blit_alpha(surface, gfx.rounded_rect((rail_w, rail_h), rail_h // 2, Palette.LINE), (rx, ry), intro)
        fill = int(rail_w * self.progress)
        if fill > rail_h:
            bar = gfx.rounded_gradient(
                (fill, rail_h), rail_h // 2, ((0.0, Palette.ROSE), (1.0, Palette.LAVENDER_DEEP)), vertical=False
            )
            gfx.blit_alpha(surface, bar, (rx, ry), intro)
            tip = gfx.soft_shadow((rail_h * 3, rail_h * 3), rail_h, max(2, int(4 * s)), 220, Palette.LAVENDER_DEEP)
            gfx.blit_center(surface, tip, (rx + fill, ry + rail_h / 2), intro * 0.9)

    def _draw_banner(self, surface: pygame.Surface) -> None:
        """'Player N' announcement when the turn passes."""
        if self.banner_player is None or self.banner_age > 1.5:
            return
        t = self.banner_age
        alpha = min(1.0, t / 0.18, max(0.0, (1.5 - t) / 0.35))
        pop = 0.85 + 0.15 * ease_out_back(t / 0.35, 2.0)
        s = self.app.ui * pop
        fonts = self.app.fonts
        color = self.player_color(self.banner_player)
        name = gfx.text(fonts.get("display", 38 * s), f"Player {self.banner_player + 1}", color)
        sub = gfx.text(fonts.get("medium", 15 * s), "your turn", Palette.INK_MUTED)
        w = name.get_width() + sub.get_width() + int(84 * s)
        h = int(70 * s)
        cx = self.app.size[0] / 2
        board_top, board_bottom = self.sprites[0].rect.top, max(sp.rect.bottom for sp in self.sprites)
        cy = (board_top + board_bottom) / 2
        glow = gfx.soft_shadow((w, h), h // 2, max(6, int(18 * s)), 170, color)
        gfx.blit_center(surface, glow, (cx, cy + 4 * s), alpha)
        pill = gfx.rounded_rect((w, h), h // 2, (255, 255, 255, 240), max(2, int(2 * s)), color)
        gfx.blit_center(surface, pill, (cx, cy), alpha)
        x = cx - w / 2 + int(28 * s)
        gfx.blit_center(surface, gfx.circle(int(16 * s), color), (x + 8 * s, cy), alpha)
        x += int(26 * s)
        gfx.blit_alpha(surface, name, (x, cy - name.get_height() / 2 - 2 * s), alpha)
        x += name.get_width() + int(12 * s)
        gfx.blit_alpha(surface, sub, (x, cy - sub.get_height() / 2 + 3 * s), alpha * (0.4 + 0.6 * bump(min(1, t))))

    def _draw_combo(self, surface: pygame.Surface) -> None:
        if self.combo_shown < 0.02 or self.game.streak < 2 and self.combo_shown < 0.02:
            return
        s = self.app.ui
        streak = max(2, self.game.streak)
        label = f"COMBO ×{streak_multiplier(streak):g}"
        text = gfx.text(self.app.fonts.get("semibold", 14 * s), label, Palette.INK_DARK, tracking=1.5 * s)
        pop = 1 + 0.22 * math.exp(-self.combo_age * 7) * math.cos(self.combo_age * 14)
        w, h = int((text.get_width() + 30 * s) * pop), int(32 * s * pop)
        cx, cy = self.hud.centerx, self.hud.bottom + int(2 * s)
        glow = gfx.soft_shadow((w, h), h // 2, max(4, int(12 * s)), 170, Palette.GOLD)
        gfx.blit_center(surface, glow, (cx, cy), self.combo_shown * 0.8)
        pill = gfx.rounded_gradient((w, h), h // 2, HONEY_STOPS)
        gfx.blit_center(surface, pill, (cx, cy), self.combo_shown)
        if pop != 1:
            text = pygame.transform.smoothscale(text, (int(text.get_width() * pop), int(text.get_height() * pop)))
        gfx.blit_center(surface, text, (cx, cy), self.combo_shown)

    def _draw_footer(self, surface: pygame.Surface) -> None:
        s = self.app.ui
        w, h = self.app.size
        if self.phase is Phase.DEALING:
            hint = "Click to skip the deal"
        elif self.multiplayer:
            hint = "Esc pause  \u00b7  R restart  \u00b7  arrows + Space to play by keyboard"
        else:
            hint = "Esc pause  \u00b7  G glimpse  \u00b7  R restart  \u00b7  arrows + Space to play by keyboard"
        text = gfx.text(self.app.fonts.get("regular", 12 * s), hint, Palette.INK_FAINT)
        gfx.blit_center(surface, text, (w / 2, h - self.footer_h / 2 - 4 * s), 0.85 * ease_out_cubic(self.age - 0.4))


class PauseModal(Modal):
    def __init__(self, scene: GameScene) -> None:
        super().__init__(scene.app)
        self.scene = scene
        app = scene.app
        self.resume = Button(app, "Resume", self.close, style="primary", icon="play")
        self.restart = Button(app, "Restart", scene.restart, icon="restart")
        self.sound = Button(app, "", self._toggle_sound)
        self.menu = Button(app, "Main menu", scene.to_menu, icon="home")
        self._sync_sound()
        self.set_widgets([self.resume, self.restart, self.sound, self.menu])
        app.audio.play("click")

    def _toggle_sound(self) -> None:
        self.app.set_sound(not self.app.save.settings.sound)
        self._sync_sound()

    def _sync_sound(self) -> None:
        on = self.app.save.settings.sound
        self.sound.label = "Sound on" if on else "Sound off"
        self.sound.icon = "sound" if on else "sound_off"

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.interactive and event.type == pygame.KEYDOWN and event.key == pygame.K_p:
            self.close()
            return
        super().handle_event(event)

    def layout(self, size: tuple[int, int]) -> None:
        s = self.app.ui
        w, h = int(420 * s), int(440 * s)
        self.panel = pygame.Rect((size[0] - w) // 2, (size[1] - h) // 2, w, h)
        bw, bh = int(300 * s), int(50 * s)
        y = self.panel.y + int(170 * s)
        for button in self.widgets:
            button.rect = pygame.Rect(self.panel.centerx - bw // 2, y, bw, bh)
            y += bh + int(12 * s)

    def draw_content(self, surface, panel, alpha) -> None:
        s = self.app.ui
        fonts = self.app.fonts
        game = self.scene.game
        over = gfx.text(fonts.get("medium", 12 * s), "PAUSED", Palette.ACCENT, tracking=4 * s)
        gfx.blit_center(surface, over, (panel.centerx, panel.y + 44 * s), alpha)
        title = gfx.text(fonts.get("display", 46 * s), "Take a breath", Palette.INK)
        gfx.blit_center(surface, title, (panel.centerx, panel.y + 88 * s), alpha)
        if self.scene.multiplayer:
            info = f"Player {game.current + 1}\u2019s turn  \u00b7  {game.matches} of {game.pairs} pairs found"
        else:
            clock = gfx.format_time(self.scene.elapsed)
            info = f"{clock}  \u00b7  {game.moves} moves  \u00b7  {game.matches} of {game.pairs} pairs"
        text = gfx.text(fonts.get("regular", 14 * s), info, Palette.INK_MUTED)
        gfx.blit_center(surface, text, (panel.centerx, panel.y + 130 * s), alpha)


class ResultsModal(Modal):
    dismissable = False
    dim = 0.5

    def __init__(self, scene: GameScene) -> None:
        super().__init__(scene.app)
        self.scene = scene
        self.final = scene.final
        self.age = 0.0
        self.stars_played = 0
        app = scene.app
        nxt = next_difficulty(scene.difficulty.key)
        label = "Rematch" if scene.multiplayer else "Play again"
        self.again = Button(app, label, scene.restart, style="primary", icon="restart")
        self.next = Button(app, f"Next: {nxt.name}", lambda: scene.play(nxt), icon="arrow_right") if nxt else None
        self.menu = Button(app, "Menu", scene.to_menu, icon="home")
        widgets = [self.again, *([self.next] if self.next else []), self.menu]
        self.set_widgets(widgets)

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.interactive and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_n and self.next:
                self.next.activate()
                return
            if event.key == pygame.K_r:
                self.again.activate()
                return
            if event.key in (pygame.K_m, pygame.K_ESCAPE):
                self.menu.activate()
                return
        super().handle_event(event)

    def layout(self, size: tuple[int, int]) -> None:
        s = self.app.ui
        w = int(640 * s)
        if self.scene.multiplayer:  # standings rows plus title and buttons
            h = int((176 + self.scene.players * 68 + 30 + 50 + 34) * s)
        else:
            h = int(610 * s)
        self.panel = pygame.Rect((size[0] - w) // 2, (size[1] - h) // 2, w, h)
        bh = int(50 * s)
        gap = int(12 * s)
        widths = [int(190 * s)] + ([int(210 * s)] if self.next else []) + [int(130 * s)]
        total = sum(widths) + gap * (len(widths) - 1)
        x = self.panel.centerx - total // 2
        y = self.panel.bottom - bh - int(34 * s)
        for button, bw in zip(self.widgets, widths):
            button.rect = pygame.Rect(x, y, bw, bh)
            x += bw + gap

    def update(self, dt: float) -> None:
        super().update(dt)
        self.age += dt
        s = self.app.ui
        while not self.scene.multiplayer and self.stars_played < 3 and self.age >= self._star_time(self.stars_played):
            i = self.stars_played
            self.stars_played += 1
            if i < self.final.stars:
                cx, cy = self._star_center(i)
                self.scene.top_effects.sparkles(cx, cy, 16, 220 * s, scale=s)
                self.app.audio.play(f"star{i}")

    @staticmethod
    def _star_time(i: int) -> float:
        return 0.45 + i * 0.3

    def _star_center(self, i: int) -> tuple[float, float]:
        s = self.app.ui
        spacing = 74 * s
        return (self.panel.centerx + (i - 1) * spacing, self.panel.y + self.offset + 204 * s + (8 * s if i != 1 else 0))

    def draw_content(self, surface, panel, alpha) -> None:
        s = self.app.ui
        fonts = self.app.fonts
        scene = self.scene
        game = scene.game
        final = self.final

        over = gfx.text(fonts.get("medium", 12 * s), "DREAM COMPLETE", Palette.ACCENT, tracking=4 * s)
        gfx.blit_center(surface, over, (panel.centerx, panel.y + 40 * s), alpha)
        if scene.multiplayer:
            self._draw_standings(surface, panel, alpha)
            return
        title = gfx.gradient_text(
            fonts.get("display", 62 * s),
            scene.difficulty.name,
            ((0.0, Palette.ROSE_DEEP), (1.0, Palette.LAVENDER_DEEP)),
        )
        gfx.blit_center(surface, title, (panel.centerx, panel.y + 90 * s), alpha)
        if scene.first_clear:
            self._pill(surface, "FIRST CLEAR", (panel.centerx, panel.y + 142 * s), alpha, Palette.LAVENDER)

        # Stars pop in one by one.
        for i in range(3):
            cx, cy = self._star_center(i)
            size = int((64 if i == 1 else 52) * s)
            t = (self.age - self._star_time(i)) / 0.45
            earned = i < final.stars
            outline = gfx.icon("star", size, Palette.LINE)
            gfx.blit_center(surface, outline, (cx, cy), alpha)
            if earned and t > 0:
                k = ease_out_back(t, 2.2)
                star = gfx.icon("star", size, Palette.GOLD)
                glow = _star_glow(size, max(4, int(10 * s)))
                d = max(1, int(size * k))
                gfx.blit_center(
                    surface,
                    pygame.transform.smoothscale(
                        glow, (int(glow.get_width() * k) or 1, int(glow.get_height() * k) or 1)
                    ),
                    (cx, cy),
                    alpha * min(1.0, t * 3),
                )
                gfx.blit_center(surface, pygame.transform.smoothscale(star, (d, d)), (cx, cy), alpha)

        # Score, counting up.
        count = ease_out_cubic((self.age - 0.3) / 1.1)
        score = gfx.text(fonts.get("semibold", 54 * s), f"{int(final.total * count):,}", Palette.INK)
        gfx.blit_center(surface, score, (panel.centerx, panel.y + 290 * s), alpha)
        if scene.new_bests.score:
            self._pill(
                surface,
                "NEW BEST",
                (panel.centerx + score.get_width() / 2 + 52 * s, panel.y + 290 * s),
                alpha,
                Palette.GOLD,
            )
        parts = [f"Pairs {final.match_points:,}"]
        if final.time_bonus:
            parts.append(f"+ Time bonus {final.time_bonus:,}")
        if final.glimpse_penalty:
            parts.append(f"− Glimpse {final.glimpse_penalty:,}")
        breakdown = gfx.text(fonts.get("regular", 14 * s), "   ".join(parts), Palette.INK_MUTED)
        gfx.blit_center(surface, breakdown, (panel.centerx, panel.y + 332 * s), alpha)

        # Stat grid.
        stats = (
            ("TIME", gfx.format_time(scene.elapsed), scene.new_bests.time),
            ("MOVES", str(game.moves), scene.new_bests.moves),
            ("ACCURACY", f"{round(game.accuracy * 100)}%", False),
            ("BEST COMBO", f"×{game.best_streak}", False),
        )
        grid_w = panel.w - int(80 * s)
        cell = grid_w / len(stats)
        top = panel.y + int(364 * s)
        box = gfx.rounded_rect((grid_w, int(96 * s)), int(18 * s), Palette.GLASS, 1, Palette.GLASS_EDGE)
        gfx.blit_alpha(surface, box, (panel.x + int(40 * s), top), alpha)
        for i, (label, value, best) in enumerate(stats):
            cx = panel.x + int(40 * s) + cell * i + cell / 2
            lab = gfx.text(fonts.get("medium", 11 * s), label, Palette.INK_FAINT, tracking=2.5 * s)
            val = gfx.text(fonts.get("semibold", 26 * s), value, Palette.GOLD_DEEP if best else Palette.INK)
            gfx.blit_center(surface, lab, (cx, top + 26 * s), alpha)
            gfx.blit_center(surface, val, (cx, top + 56 * s), alpha)
            if best:
                self._pill(surface, "BEST", (cx, top + 84 * s), alpha, Palette.GOLD, small=True)

    def _draw_standings(self, surface, panel, alpha) -> None:
        """Multiplayer results: the winner (or a tie) and everyone's pairs."""
        s = self.app.ui
        fonts = self.app.fonts
        scene = self.scene
        game = scene.game
        leaders = game.leaders
        if len(leaders) == 1:
            color = scene.player_color(leaders[0])
            headline = f"Player {leaders[0] + 1} wins!"
            stops = ((0.0, color), (1.0, lerp_color(color, Palette.LAVENDER_DEEP, 0.5)))
        else:
            headline = "It\u2019s a tie!"
            stops = ((0.0, Palette.ROSE_DEEP), (1.0, Palette.LAVENDER_DEEP))
        title = gfx.gradient_text(fonts.get("display", 58 * s), headline, stops)
        gfx.blit_center(surface, title, (panel.centerx, panel.y + 94 * s), alpha)
        sub = (
            f"{scene.difficulty.name}  \u00b7  {gfx.format_time(scene.elapsed)}  \u00b7  {game.moves} moves"
            if len(leaders) == 1
            else " and ".join(f"Player {i + 1}" for i in leaders) + " share the dream"
        )
        text = gfx.text(fonts.get("regular", 14 * s), sub, Palette.INK_MUTED)
        gfx.blit_center(surface, text, (panel.centerx, panel.y + 140 * s), alpha)

        order = sorted(range(game.players), key=lambda i: (-game.player_pairs[i], -game.player_points[i], i))
        row_w, row_h, gap = panel.w - int(96 * s), int(58 * s), int(10 * s)
        x = panel.x + (panel.w - row_w) // 2
        y = panel.y + int(176 * s)
        best = game.player_pairs[order[0]]
        for rank, i in enumerate(order):
            t = ease_out_cubic((self.age - 0.35 - rank * 0.12) / 0.5)
            if t <= 0:
                continue
            color = scene.player_color(i)
            winner = game.player_pairs[i] == best
            ry = y + rank * (row_h + gap) + int((1 - t) * 16 * s)
            fill = lerp_color(color, (255, 255, 255), 0.78) + (255,) if winner else Palette.GLASS
            row = gfx.rounded_rect(
                (row_w, row_h),
                int(18 * s),
                fill,
                max(1, int(2 * s)) if winner else 1,
                color if winner else Palette.GLASS_EDGE,
            )
            gfx.blit_alpha(surface, row, (x, ry), alpha * t)
            cy = ry + row_h / 2
            rank_text = gfx.text(fonts.get("semibold", 18 * s), str(rank + 1), Palette.INK_FAINT)
            gfx.blit_center(surface, rank_text, (x + 26 * s, cy), alpha * t)
            gfx.blit_center(surface, gfx.circle(int(16 * s), color), (x + 56 * s, cy), alpha * t)
            name = gfx.text(fonts.get("semibold", 19 * s), f"Player {i + 1}", Palette.INK)
            gfx.blit_alpha(surface, name, (x + int(74 * s), cy - name.get_height() / 2), alpha * t)
            if winner:
                trophy = gfx.icon("trophy", int(20 * s), Palette.GOLD_DEEP)
                gfx.blit_center(surface, trophy, (x + int(84 * s) + name.get_width() + 12 * s, cy), alpha * t)
            pairs = game.player_pairs[i]
            value = gfx.text(fonts.get("semibold", 22 * s), f"{pairs} pair{'s' if pairs != 1 else ''}", color)
            points = gfx.text(fonts.get("regular", 13 * s), f"{game.player_points[i]:,} pts", Palette.INK_MUTED)
            vx = x + row_w - int(22 * s)
            gfx.blit_alpha(surface, value, (vx - value.get_width(), cy - value.get_height() / 2 - 7 * s), alpha * t)
            gfx.blit_alpha(surface, points, (vx - points.get_width(), cy + 8 * s), alpha * t)

    def _pill(self, surface, label, center, alpha, color, small=False) -> None:
        s = self.app.ui
        text = gfx.text(
            self.app.fonts.get("semibold", (10 if small else 11) * s), label, Palette.INK_DARK, tracking=1.5 * s
        )
        w, h = text.get_width() + int(18 * s), int((18 if small else 22) * s)
        gfx.blit_center(surface, gfx.rounded_rect((w, h), h // 2, color), center, alpha)
        gfx.blit_center(surface, text, center, alpha)
