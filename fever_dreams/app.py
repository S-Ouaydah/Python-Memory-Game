"""Application shell: window, main loop, scene switching and global keys."""

from __future__ import annotations

import random
import warnings
from collections.abc import Callable
from datetime import datetime

import pygame

from . import gfx
from .assets import CARD_DIR, CardArt, Fonts, crop_to_aspect
from .audio import Audio
from .background import DreamBackground
from .config import DESIGN_SIZE, FPS, MIN_WINDOW_SIZE, TITLE, WINDOW_SIZE, Palette
from .storage import SaveData
from .tween import clamp

FADE_OUT = 0.25
FADE_IN = 0.35


class App:
    def __init__(
        self,
        *,
        size: tuple[int, int] | None = None,
        fullscreen: bool | None = None,
        seed: int | None = None,
        save: SaveData | None = None,
        fps: int = FPS,
    ) -> None:
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        pygame.key.set_repeat(320, 60)
        self.save = save or SaveData.load()
        self.rng = random.Random(seed)
        self.fps = fps
        pygame.display.set_caption(TITLE)
        self._windowed_size = size or self._default_window_size()
        self.fullscreen = False
        want_fullscreen = self.save.settings.fullscreen if fullscreen is None else fullscreen
        self.screen = self._make_window(want_fullscreen)
        self._set_icon()

        self.clock = pygame.time.Clock()
        self.fonts = Fonts()
        self.art = CardArt()
        self.audio = Audio(self.save.settings.sound)
        self.background = DreamBackground(self.size, random.Random(self.rng.random()))
        self.background.ambient = self.save.settings.ambient

        self.running = True
        self.keyboard_mode = False
        self.want_hand_cursor = False
        self._hand_cursor = False
        self._next_scene: Callable[[], object] | None = None
        self._fade = 0.0  # 0 = scene fully visible, 1 = only the background
        self._backdrop = pygame.Surface(self.size).convert()
        self._toast: pygame.Surface | None = None
        self._toast_age = 0.0

        from .scenes.menu import MenuScene

        self.scene = MenuScene(self)
        self.scene.enter()

    # -- window --------------------------------------------------------------

    @property
    def size(self) -> tuple[int, int]:
        return self.screen.get_size()

    @property
    def ui(self) -> float:
        """UI scale factor relative to the design resolution."""
        w, h = self.size
        return clamp(min(w / DESIGN_SIZE[0], h / DESIGN_SIZE[1]), 0.7, 2.0)

    @staticmethod
    def _default_window_size() -> tuple[int, int]:
        try:
            desk_w, desk_h = pygame.display.get_desktop_sizes()[0]
        except (pygame.error, IndexError):
            return WINDOW_SIZE
        return (min(WINDOW_SIZE[0], int(desk_w * 0.92)), min(WINDOW_SIZE[1], int(desk_h * 0.86)))

    def _make_window(self, fullscreen: bool) -> pygame.Surface:
        if fullscreen:
            screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            screen = pygame.display.set_mode(self._windowed_size, pygame.RESIZABLE)
            # pygame-ce has no non-deprecated way to reach the display-module
            # window yet; without it the window simply has no minimum size.
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    pygame.Window.from_display_module().minimum_size = MIN_WINDOW_SIZE
            except (AttributeError, pygame.error):
                pass
        self.fullscreen = fullscreen
        return screen

    def _set_icon(self) -> None:
        try:
            art = crop_to_aspect(pygame.image.load(str(CARD_DIR / "card_back.png")), 1.0, 0.4)
            icon = pygame.transform.smoothscale(art, (64, 64)).convert_alpha()
            icon.blit(gfx.rounded_rect((64, 64), 14, (255, 255, 255)), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            pygame.display.set_icon(icon)
        except (OSError, pygame.error):
            pass

    def toggle_fullscreen(self) -> None:
        if not self.fullscreen:
            self._windowed_size = self.size
        self.screen = self._make_window(not self.fullscreen)
        self.save.settings.fullscreen = self.fullscreen
        self.save.save()
        self._on_resize()

    def _on_resize(self) -> None:
        self.screen = pygame.display.get_surface()
        if self._backdrop.get_size() == self.size:
            return
        self._backdrop = pygame.Surface(self.size).convert()
        self.background.resize(self.size)
        self.scene.resize(self.size)

    # -- settings shared by several scenes --------------------------------------

    def set_sound(self, on: bool) -> None:
        self.save.settings.sound = self.audio.enabled = on
        self.save.save()

    def set_ambient(self, on: bool) -> None:
        self.save.settings.ambient = self.background.ambient = on
        self.save.save()

    # -- scenes ----------------------------------------------------------------

    @property
    def transitioning(self) -> bool:
        return self._next_scene is not None

    def switch(self, factory: Callable[[], object]) -> None:
        """Cross-fade to the scene built by ``factory`` (over the live backdrop)."""
        if self._next_scene is None:
            self._next_scene = factory

    def toast(self, message: str) -> None:
        font = self.fonts.get("medium", 15 * self.ui)
        self._toast = gfx.text(font, message, Palette.INK)
        self._toast_age = 0.0

    def screenshot(self) -> None:
        folder = self.save.path.parent / "screenshots"
        path = folder / f"fever-dreams-{datetime.now():%Y%m%d-%H%M%S}.png"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            pygame.image.save(self.screen, str(path))
        except (OSError, pygame.error):
            self.toast("Couldn't save the screenshot")
            return
        self.toast(f"Screenshot saved to {path}")

    def quit(self) -> None:
        self.running = False

    # -- loop --------------------------------------------------------------------

    def run(self, max_frames: int | None = None) -> None:
        frames = 0
        try:
            while self.running:
                dt = min(self.clock.tick(self.fps) / 1000.0, 1 / 20)
                self.step(dt, pygame.event.get())
                pygame.display.flip()
                frames += 1
                if max_frames is not None and frames >= max_frames:
                    break
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self.save.save()
        pygame.quit()

    def step(self, dt: float, events: list[pygame.event.Event]) -> None:
        self.want_hand_cursor = False
        for event in events:
            self._dispatch(event)
        self._update(dt)
        self._draw()

    def _dispatch(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.quit()
            return
        if event.type in (pygame.VIDEORESIZE, pygame.WINDOWSIZECHANGED):
            self._on_resize()
            return
        if event.type == pygame.WINDOWFOCUSLOST:
            self.scene.focus_lost()
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11 or (event.key == pygame.K_RETURN and event.mod & pygame.KMOD_ALT):
                self.toggle_fullscreen()
                return
            if event.key == pygame.K_F12:
                self.screenshot()
                return
            self.keyboard_mode = True
        elif event.type == pygame.MOUSEMOTION and (abs(event.rel[0]) + abs(event.rel[1])) > 2:
            self.keyboard_mode = False
        if not self.transitioning:
            self.scene.handle_event(event)

    def _update(self, dt: float) -> None:
        if self._next_scene is not None:
            self._fade = min(1.0, self._fade + dt / FADE_OUT)
            if self._fade >= 1.0:
                self.scene.exit()
                self.scene = self._next_scene()
                self._next_scene = None
                self.scene.enter()
        elif self._fade > 0:
            self._fade = max(0.0, self._fade - dt / FADE_IN)
        self.background.update(dt)
        self.scene.update(dt)
        if self._toast is not None:
            self._toast_age += dt
            if self._toast_age > 3.0:
                self._toast = None
        if self.want_hand_cursor != self._hand_cursor:
            self._hand_cursor = self.want_hand_cursor
            try:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if self._hand_cursor else pygame.SYSTEM_CURSOR_ARROW)
            except pygame.error:
                pass

    def _draw(self) -> None:
        screen = self.screen
        self.background.draw(screen)
        if self._fade > 0:
            self._backdrop.blit(screen, (0, 0))
        self.scene.draw(screen)
        if self._fade > 0:
            gfx.blit_alpha(screen, self._backdrop, (0, 0), self._fade)
        if self._toast is not None:
            self._draw_toast(screen)

    def _draw_toast(self, screen: pygame.Surface) -> None:
        s = self.ui
        label = self._toast
        w, h = label.get_width() + int(40 * s), int(44 * s)
        x = (self.size[0] - w) // 2
        y = self.size[1] - h - int(28 * s)
        alpha = min(1.0, self._toast_age * 6, (3.0 - self._toast_age) * 2)
        shadow = gfx.soft_shadow((w, h), h // 2, max(4, int(10 * s)), 70, Palette.SHADOW)
        gfx.blit_center(screen, shadow, (x + w / 2, y + h / 2 + 4 * s), alpha)
        pill = gfx.rounded_rect((w, h), h // 2, (255, 255, 255, 236), 1, (*Palette.ROSE, 200))
        gfx.blit_alpha(screen, pill, (x, y), alpha)
        gfx.blit_center(screen, label, (x + w / 2, y + h / 2), alpha)
