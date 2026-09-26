"""Static configuration: window, timings, difficulty presets and the colour palette."""

from __future__ import annotations

from dataclasses import dataclass

TITLE = "Fever Dreams"

#: Default window size and the smallest size the window may be resized to.
WINDOW_SIZE = (1280, 800)
MIN_WINDOW_SIZE = (960, 640)

#: The resolution the UI is designed at; everything scales relative to it.
DESIGN_SIZE = (1280, 800)

FPS = 60

#: Width / height of every card. The source art is cropped to this ratio.
CARD_ASPECT = 0.64

# Gameplay timings, in seconds.
FLIP_DURATION = 0.36
MISMATCH_DELAY = 0.9  # how long a wrong pair stays visible before turning back
GLIMPSE_DURATION = 1.4
DEAL_DURATION = 0.6
DEAL_STAGGER = 0.03
WIN_CELEBRATION = 1.1  # pause between the final match and the results panel


@dataclass(frozen=True)
class Difficulty:
    key: str
    name: str
    tagline: str
    pairs: int
    #: Finishing faster than this (seconds) earns a time bonus.
    par_time: float


DIFFICULTIES: tuple[Difficulty, ...] = (
    Difficulty("serene", "Serene", "A gentle first dream", 6, 60),
    Difficulty("drift", "Drift", "Petals on the wind", 10, 120),
    Difficulty("reverie", "Reverie", "Lost in the blossoms", 15, 210),
    Difficulty("fever", "Fever", "Every dreamer at once", 22, 360),
)

DIFFICULTY_BY_KEY = {d.key: d for d in DIFFICULTIES}


def next_difficulty(key: str) -> Difficulty | None:
    """The preset after ``key``, or ``None`` if ``key`` is the hardest."""
    keys = [d.key for d in DIFFICULTIES]
    position = keys.index(key)
    return DIFFICULTIES[position + 1] if position + 1 < len(DIFFICULTIES) else None


class Palette:
    """Night-time blossom palette, pulled from the card art."""

    BG_TOP = (16, 11, 34)
    BG_MID = (38, 19, 60)
    BG_BOTTOM = (20, 11, 36)

    INK = (247, 240, 252)
    INK_SOFT = (214, 200, 236)
    INK_MUTED = (168, 152, 198)
    INK_FAINT = (132, 118, 166)
    INK_DARK = (38, 20, 52)

    GOLD = (242, 196, 104)
    GOLD_LIGHT = (255, 230, 168)
    GOLD_DEEP = (206, 146, 64)
    ROSE = (255, 146, 196)
    ROSE_DEEP = (220, 96, 158)
    LAVENDER = (184, 158, 255)
    SKY = (140, 208, 255)
    DANGER = (255, 112, 138)

    PETALS = ((255, 196, 222), (255, 170, 205), (250, 222, 238), (236, 180, 230))
