"""Loading and caching of fonts and card art."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import pygame

from . import gfx
from .config import CARD_ASPECT, Palette

ASSET_DIR = Path(__file__).resolve().parent / "assets"
CARD_DIR = ASSET_DIR / "cards"
FONT_DIR = ASSET_DIR / "fonts"
FACE_COUNT = 22

FONT_FILES = {
    "display": "CormorantGaramond-SemiBoldItalic.ttf",
    "display_medium": "CormorantGaramond-MediumItalic.ttf",
    "serif": "CormorantGaramond-SemiBold.ttf",
    "light": "Outfit-Light.ttf",
    "regular": "Outfit-Regular.ttf",
    "medium": "Outfit-Medium.ttf",
    "semibold": "Outfit-SemiBold.ttf",
}


class Fonts:
    """Font objects by role and pixel size, falling back to pygame's default."""

    #: Small print never shrinks below this, however small the window.
    MIN_PX = 10

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], pygame.font.Font] = {}

    def get(self, role: str, size: float) -> pygame.font.Font:
        px = max(self.MIN_PX, int(round(size)))
        key = (role, px)
        font = self._cache.get(key)
        if font is None:
            try:
                font = pygame.font.Font(FONT_DIR / FONT_FILES[role], px)
            except (OSError, pygame.error):
                font = pygame.font.Font(None, int(px * 1.3))
            self._cache[key] = font
        return font


def crop_to_aspect(image: pygame.Surface, aspect: float, bias_y: float = 0.3) -> pygame.Surface:
    """Crop to width/height ``aspect``. ``bias_y`` picks where a vertical crop sits."""
    w, h = image.get_size()
    if w / h > aspect:
        new_w = int(h * aspect)
        return image.subsurface(((w - new_w) // 2, 0, new_w, h)).copy()
    new_h = int(w / aspect)
    return image.subsurface((0, int((h - new_h) * bias_y), w, new_h)).copy()


def card_radius(width: int) -> int:
    return max(4, int(width * 0.075))


class CardArt:
    """The 22 dreamer faces and the card back, scaled and framed on demand.

    Scaled cards are cached per size; only the few most recent sizes are
    kept so dragging the window edge doesn't pile up memory.
    """

    MAX_SIZES = 4

    def __init__(self) -> None:
        self.faces = [self._load(CARD_DIR / f"card{i}.png", 0.3) for i in range(1, FACE_COUNT + 1)]
        self.back_art = self._load(CARD_DIR / "card_back.png", 0.28)
        self._sizes: OrderedDict[tuple[int, int], dict] = OrderedDict()

    @staticmethod
    def _load(path: Path, bias: float) -> pygame.Surface:
        image = pygame.image.load(str(path))
        image = image.convert() if pygame.display.get_surface() else image
        return crop_to_aspect(image, CARD_ASPECT, bias)

    @property
    def count(self) -> int:
        return len(self.faces)

    def _bucket(self, size: tuple[int, int]) -> dict:
        size = (int(size[0]), int(size[1]))
        bucket = self._sizes.get(size)
        if bucket is None:
            bucket = self._sizes[size] = {}
            while len(self._sizes) > self.MAX_SIZES:
                self._sizes.popitem(last=False)
        else:
            self._sizes.move_to_end(size)
        return bucket

    def face(self, index: int, size: tuple[int, int]) -> pygame.Surface:
        bucket = self._bucket(size)
        surf = bucket.get(index)
        if surf is None:
            surf = bucket[index] = self._frame(self.faces[index], size, back=False)
        return surf

    def back(self, size: tuple[int, int]) -> pygame.Surface:
        bucket = self._bucket(size)
        surf = bucket.get("back")
        if surf is None:
            surf = bucket["back"] = self._frame(self.back_art, size, back=True)
        return surf

    @staticmethod
    def _frame(src: pygame.Surface, size: tuple[int, int], back: bool) -> pygame.Surface:
        w, h = int(size[0]), int(size[1])
        radius = card_radius(w)
        img = pygame.transform.smoothscale(src, (w, h)).convert_alpha()
        if back:
            # Calm the glare so revealed faces stand out, deepen the edges and
            # add an engraved inner frame.
            img.fill((226, 218, 232), special_flags=pygame.BLEND_RGB_MULT)
            img.blit(
                gfx.gradient(
                    (w, h), ((0.0, (0, 0, 0, 70)), (0.25, (0, 0, 0, 0)), (0.75, (0, 0, 0, 0)), (1.0, (0, 0, 0, 90)))
                ),
                (0, 0),
            )
            inset = max(3, int(w * 0.055))
            frame = gfx.rounded_outline(
                (w - 2 * inset, h - 2 * inset),
                max(2, radius - inset // 2),
                (*Palette.GOLD_LIGHT, 170),
                max(1.0, w / 160),
            )
            img.blit(frame, (inset, inset))
        # Soft top sheen, like a glossy print.
        img.blit(gfx.gradient((w, h), ((0.0, (255, 255, 255, 34)), (0.35, (255, 255, 255, 0)))), (0, 0))
        img.blit(gfx.rounded_rect((w, h), radius, (255, 255, 255)), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        edge_color = (*Palette.GOLD_LIGHT, 150) if back else (255, 255, 255, 80)
        img.blit(gfx.rounded_outline((w, h), radius, edge_color, max(1.0, w / 150)), (0, 0))
        return img

    def shadow(self, size: tuple[int, int]) -> pygame.Surface:
        w = int(size[0])
        return gfx.soft_shadow(size, card_radius(w), max(4, int(w * 0.07)), alpha=160, color=(6, 2, 14))

    def halo(self, size: tuple[int, int], color, alpha: int = 210) -> pygame.Surface:
        """A soft coloured glow around a card-sized shape; blit it centred."""
        w = int(size[0])
        return gfx.soft_shadow(size, card_radius(w), max(5, int(w * 0.08)), alpha=alpha, color=tuple(color[:3]))
