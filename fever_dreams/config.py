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
    Difficulty("delirium", "Delirium", "Fifty pairs, reflections and all", 50, 900),
)

DIFFICULTY_BY_KEY = {d.key: d for d in DIFFICULTIES}


def next_difficulty(key: str) -> Difficulty | None:
    """The preset after ``key``, or ``None`` if ``key`` is the hardest."""
    keys = [d.key for d in DIFFICULTIES]
    position = keys.index(key)
    return DIFFICULTIES[position + 1] if position + 1 < len(DIFFICULTIES) else None


class Palette:
    """Soft pastel palette, pulled from the blossoms and gowns in the card art."""

    # Backdrop: lavender sky melting into blush and cream.
    BG_TOP = (232, 225, 251)
    BG_MID = (250, 230, 242)
    BG_BOTTOM = (255, 239, 228)

    # Text, darkest to lightest.
    INK = (62, 44, 88)
    INK_SOFT = (92, 74, 120)
    INK_MUTED = (126, 110, 154)
    INK_FAINT = (160, 146, 186)
    INK_DARK = (66, 40, 84)  # text on pastel fills

    # Pastels, each with a deeper tone for text and strokes on a light ground.
    ROSE = (247, 170, 202)
    ROSE_DEEP = (218, 100, 150)
    LAVENDER = (194, 176, 246)
    LAVENDER_DEEP = (134, 108, 212)
    SKY = (164, 210, 247)
    SKY_DEEP = (78, 146, 220)
    MINT = (168, 226, 202)
    MINT_DEEP = (58, 164, 128)
    PEACH = (255, 200, 172)
    PEACH_DEEP = (228, 128, 84)
    BUTTER = (255, 230, 168)
    GOLD = (238, 190, 104)
    GOLD_LIGHT = (255, 230, 172)
    GOLD_DEEP = (198, 140, 58)
    DANGER = (232, 96, 124)

    # Semantic roles.
    ACCENT = ROSE_DEEP  # overlines, section labels, scores
    FOCUS = SKY_DEEP  # keyboard focus ring
    LINE = (118, 94, 160, 60)  # hairlines, tracks, empty stars
    SHADOW = (92, 60, 128)
    GLASS = (255, 255, 255, 140)
    GLASS_HOVER = (255, 255, 255, 222)
    GLASS_EDGE = (255, 255, 255, 225)
    PANEL = (255, 255, 255, 190)
    VEIL = (226, 214, 246)  # haze behind dialogs

    PRIMARY = ((0.0, (255, 204, 224)), (1.0, (212, 192, 252)))  # rose to lilac
    HONEY = ((0.0, (255, 236, 186)), (1.0, (246, 200, 120)))
    PETALS = ((244, 158, 194), (250, 182, 210), (236, 170, 224), (255, 198, 218))

    #: One colour per player in hot-seat games.
    PLAYERS = ((226, 112, 162), (58, 170, 132), (82, 148, 224), (232, 138, 82))
