"""Scene and modal-dialog base classes."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import pygame

from .. import gfx
from ..tween import approach, ease_out_cubic
from ..widgets import FocusGroup, Widget, draw_panel

if TYPE_CHECKING:
    from ..app import App


class Scene:
    def __init__(self, app: App) -> None:
        self.app = app

    def enter(self) -> None:
        pass

    def exit(self) -> None:
        pass

    def resize(self, size: tuple[int, int]) -> None:
        pass

    def focus_lost(self) -> None:
        pass

    def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        pass


class Modal:
    """A centred glass panel over a dimmed screen, with its own widgets.

    Subclasses build widgets in ``__init__``, position them in ``layout`` and
    paint their content in ``draw_content``. Esc or a click outside the panel
    calls ``dismiss`` (which closes by default).
    """

    dim = 0.55
    dismissable = True

    def __init__(self, app: App) -> None:
        self.app = app
        self.widgets: list[Widget] = []
        self.focus = FocusGroup()
        self.panel = pygame.Rect(0, 0, 0, 0)
        self.shown = 0.0
        self.closing = False
        self.closed = False
        self._veil: pygame.Surface | None = None

    # geometry ------------------------------------------------------------------

    def layout(self, size: tuple[int, int]) -> None:
        raise NotImplementedError

    def set_widgets(self, widgets: Sequence[Widget], focus: int = 0) -> None:
        self.widgets = list(widgets)
        self.focus.set(self.widgets, focus)

    # lifecycle -----------------------------------------------------------------

    def close(self) -> None:
        self.closing = True

    def dismiss(self) -> None:
        self.close()

    @property
    def interactive(self) -> bool:
        return not self.closing and self.shown > 0.6

    def handle_event(self, event: pygame.event.Event) -> None:
        if not self.interactive:
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.dismissable:
                self.dismiss()
            return
        for widget in self.widgets:
            if widget.handle_event(event):
                return
        if (
            event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.dismissable
            and not self.panel.collidepoint(event.pos)
        ):
            self.dismiss()
            return
        self.focus.handle_key(event)

    def update(self, dt: float) -> None:
        self.shown = approach(self.shown, 0.0 if self.closing else 1.0, 12, dt)
        if self.closing and self.shown < 0.01:
            self.closed = True
        mouse = pygame.mouse.get_pos() if self.interactive else (-1, -1)
        for widget in self.widgets:
            widget.update(dt, mouse)

    # drawing -------------------------------------------------------------------

    @property
    def alpha(self) -> float:
        return ease_out_cubic(self.shown)

    @property
    def offset(self) -> int:
        return int((1 - self.alpha) * 24 * self.app.ui)

    def draw(self, surface: pygame.Surface) -> None:
        alpha = self.alpha
        if alpha <= 0.01:
            return
        size = surface.get_size()
        if self._veil is None or self._veil.get_size() != size:
            self._veil = pygame.Surface(size, pygame.SRCALPHA)
            self._veil.fill((8, 4, 18, int(255 * self.dim)))
        gfx.blit_alpha(surface, self._veil, (0, 0), alpha)
        panel = self.panel.move(0, self.offset)
        draw_panel(surface, panel, int(26 * self.app.ui), alpha, self.app.ui)
        self.draw_content(surface, panel, alpha)
        for widget in self.widgets:
            widget.rect.y += self.offset
            widget.draw(surface, alpha)
            widget.rect.y -= self.offset

    def draw_content(self, surface: pygame.Surface, panel: pygame.Rect, alpha: float) -> None:
        pass
