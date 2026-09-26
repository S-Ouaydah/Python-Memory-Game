"""Responsive board layout: fit N cards of a fixed aspect ratio into a box."""

from __future__ import annotations

import math
from dataclasses import dataclass

Rect = tuple[int, int, int, int]


@dataclass(frozen=True)
class Grid:
    cols: int
    rows: int
    card_w: int
    card_h: int
    gap: int
    rects: tuple[Rect, ...]


def compute_grid(
    count: int,
    area: Rect,
    aspect: float,
    gap_ratio: float = 0.1,
    max_card_w: float | None = None,
) -> Grid:
    """Choose the column count that gives the largest cards for ``area``.

    ``aspect`` is card width / height and the gap between cards is
    ``gap_ratio`` times the card width. A short last row is centred, and
    layouts with empty slots are slightly penalised so full grids win ties.
    """
    if count <= 0:
        raise ValueError("count must be positive")
    ax, ay, aw, ah = area
    area_ratio = aw / ah if ah else 1.0

    best_key: tuple[float, ...] | None = None
    best: tuple[int, int, float] = (count, 1, 0.0)
    for cols in range(1, count + 1):
        rows = math.ceil(count / cols)
        empty = rows * cols - count
        if empty >= cols:  # would leave a whole row empty
            continue
        fit_w = aw / (cols + (cols - 1) * gap_ratio)
        fit_h = ah / (rows / aspect + (rows - 1) * gap_ratio)
        width = min(fit_w, fit_h)
        if max_card_w is not None:
            width = min(width, max_card_w)
        grid_ratio = (cols * aspect) / rows
        key = (
            round(width * (1 - 0.04 * empty), 1),
            -empty,
            -abs(math.log(grid_ratio / area_ratio)) if area_ratio > 0 else 0.0,
        )
        if best_key is None or key > best_key:
            best_key, best = key, (cols, rows, width)

    cols, rows, width = best
    card_w = max(1, int(width))
    card_h = max(1, int(width / aspect))
    gap = int(round(width * gap_ratio))
    top = ay + (ah - (rows * card_h + (rows - 1) * gap)) // 2

    rects = []
    for i in range(count):
        row, col = divmod(i, cols)
        in_row = min(cols, count - row * cols)
        left = ax + (aw - (in_row * card_w + (in_row - 1) * gap)) // 2
        rects.append((left + col * (card_w + gap), top + row * (card_h + gap), card_w, card_h))
    return Grid(cols, rows, card_w, card_h, gap, tuple(rects))
