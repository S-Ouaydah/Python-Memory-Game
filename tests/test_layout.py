import pytest

from fever_dreams.layout import compute_grid

ASPECT = 0.64


def overlaps(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


@pytest.mark.parametrize("count", [12, 20, 30, 44])
@pytest.mark.parametrize("area", [(0, 0, 1200, 640), (40, 100, 1840, 920), (0, 0, 900, 900)])
def test_cards_fit_inside_area_without_overlap(count, area):
    grid = compute_grid(count, area, ASPECT)
    ax, ay, aw, ah = area
    assert len(grid.rects) == count
    for x, y, w, h in grid.rects:
        assert ax <= x and x + w <= ax + aw
        assert ay <= y and y + h <= ay + ah
        assert (w, h) == (grid.card_w, grid.card_h)
    for i, a in enumerate(grid.rects):
        for b in grid.rects[i + 1 :]:
            assert not overlaps(a, b)


def test_wide_area_prefers_wide_grid():
    grid = compute_grid(12, (0, 0, 1200, 640), ASPECT)
    assert (grid.cols, grid.rows) == (6, 2)


def test_short_last_row_is_centred():
    grid = compute_grid(5, (0, 0, 1000, 1000), 1.0, gap_ratio=0.0)
    last_row = [r for r in grid.rects if r[1] == max(r[1] for r in grid.rects)]
    assert len(last_row) < grid.cols
    left = min(r[0] for r in last_row)
    right = max(r[0] + r[2] for r in last_row)
    assert abs(left - (1000 - right)) <= 1


def test_max_card_width_is_respected():
    grid = compute_grid(4, (0, 0, 3000, 2000), ASPECT, max_card_w=200)
    assert grid.card_w <= 200


def test_rejects_empty_board():
    with pytest.raises(ValueError):
        compute_grid(0, (0, 0, 100, 100), ASPECT)
