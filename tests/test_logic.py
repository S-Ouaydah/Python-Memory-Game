import random

import pytest

from fever_dreams.logic import (
    BASE_PAIR_POINTS,
    GLIMPSE_COST,
    CardState,
    MemoryGame,
    Outcome,
    star_rating,
    streak_multiplier,
)


def make_game(pairs=4, seed=1, **kwargs):
    return MemoryGame(list(range(pairs)), rng=random.Random(seed), **kwargs)


def pair_indices(game):
    """Map each face to the two indices it sits at."""
    where = {}
    for i, card in enumerate(game.cards):
        where.setdefault(card.face, []).append(i)
    return where


def mismatched_pair(game):
    where = pair_indices(game)
    faces = list(where)
    return where[faces[0]][0], where[faces[1]][0]


def test_deck_contains_each_face_twice():
    game = make_game(pairs=6)
    assert len(game.cards) == 12
    assert all(len(v) == 2 for v in pair_indices(game).values())
    assert all(c.state is CardState.HIDDEN for c in game.cards)


def test_rejects_bad_faces():
    with pytest.raises(ValueError):
        MemoryGame([])
    with pytest.raises(ValueError):
        MemoryGame([1, 1, 2])


def test_seeded_shuffle_is_deterministic():
    a = [c.face for c in make_game(seed=7).cards]
    b = [c.face for c in make_game(seed=7).cards]
    assert a == b


def test_match_scores_and_locks_cards():
    game = make_game()
    i, j = pair_indices(game)[0]
    first = game.flip(i)
    assert first.outcome is Outcome.FIRST
    assert game.first == i
    result = game.flip(j)
    assert result.outcome is Outcome.MATCH
    assert result.partner == i
    assert result.points == BASE_PAIR_POINTS
    assert game.cards[i].state is game.cards[j].state is CardState.MATCHED
    assert (game.moves, game.matches, game.streak) == (1, 1, 1)
    assert game.first is None


def test_mismatch_stays_pending_until_resolved():
    game = make_game()
    a, b = mismatched_pair(game)
    game.flip(a)
    result = game.flip(b)
    assert result.outcome is Outcome.MISMATCH
    assert game.pending == (a, b)
    assert game.cards[a].state is CardState.REVEALED
    assert game.resolve_mismatch() == (a, b)
    assert game.pending is None
    assert game.cards[a].state is game.cards[b].state is CardState.HIDDEN
    assert game.resolve_mismatch() == ()


def test_flipping_during_pending_mismatch_resolves_it():
    """The original game let a third click corrupt its state; now it just continues."""
    game = make_game()
    a, b = mismatched_pair(game)
    game.flip(a)
    game.flip(b)
    third = next(i for i in range(len(game.cards)) if i not in (a, b))
    result = game.flip(third)
    assert result.outcome is Outcome.FIRST
    assert result.hidden == (a, b)
    assert game.first == third
    revealed = [i for i, c in enumerate(game.cards) if c.state is CardState.REVEALED]
    assert revealed == [third]


def test_clicking_a_pending_card_dismisses_the_pair():
    game = make_game()
    a, b = mismatched_pair(game)
    game.flip(a)
    game.flip(b)
    result = game.flip(a)
    assert result.outcome is Outcome.IGNORED
    assert result.hidden == (a, b)
    assert game.cards[a].state is CardState.HIDDEN


def test_same_card_twice_is_ignored():
    game = make_game()
    game.flip(0)
    result = game.flip(0)
    assert result.outcome is Outcome.IGNORED
    assert game.moves == 0
    assert game.first == 0


def test_matched_cards_are_ignored():
    game = make_game()
    i, j = pair_indices(game)[0]
    game.flip(i)
    game.flip(j)
    assert game.flip(i).outcome is Outcome.IGNORED
    assert not game.is_selectable(i)


def test_out_of_range_index():
    with pytest.raises(IndexError):
        make_game().flip(99)


def test_streak_multiplier_and_reset():
    game = make_game(pairs=5)
    where = pair_indices(game)
    points = []
    for face in (0, 1, 2):
        game.flip(where[face][0])
        points.append(game.flip(where[face][1]).points)
    assert points == [100, 150, 200]
    assert game.best_streak == 3
    game.flip(where[3][0])
    game.flip(where[4][0])
    assert game.streak == 0
    assert game.best_streak == 3


def test_multiplier_is_capped():
    assert streak_multiplier(1) == 1.0
    assert streak_multiplier(2) == 1.5
    assert streak_multiplier(50) == 3.0


def test_finishing_the_board():
    game = make_game(pairs=3)
    last = None
    for i, j in pair_indices(game).values():
        game.flip(i)
        last = game.flip(j)
    assert last.finished and game.finished
    assert game.accuracy == 1.0
    assert game.flip(0).outcome is Outcome.IGNORED


def test_glimpse_is_limited_and_costs_points():
    game = make_game(glimpses=1)
    assert game.use_glimpse()
    assert not game.use_glimpse()
    assert game.score == 0  # never negative
    i, j = pair_indices(game)[0]
    game.flip(i)
    game.flip(j)
    assert game.score == max(0, BASE_PAIR_POINTS - GLIMPSE_COST)


def test_final_score_includes_time_bonus():
    game = make_game(pairs=2)
    for i, j in pair_indices(game).values():
        game.flip(i)
        game.flip(j)
    final = game.final_score(elapsed=10.0, par_time=30.0)
    assert final.time_bonus == 200
    assert final.total == final.match_points + 200
    assert final.stars == 3
    assert game.final_score(elapsed=99, par_time=30).time_bonus == 0


def test_star_rating_thresholds():
    assert star_rating(10, 6) == 3  # ceil(6 * 1.75) == 11
    assert star_rating(11, 6) == 3
    assert star_rating(12, 6) == 2
    assert star_rating(15, 6) == 2
    assert star_rating(16, 6) == 1
    assert star_rating(0, 0) == 0


# -- hot-seat multiplayer --------------------------------------------------------


def test_players_take_turns_on_a_miss_and_keep_turn_on_a_match():
    game = make_game(pairs=4, players=3)
    where = pair_indices(game)
    assert game.current == 0

    game.flip(where[0][0])
    match = game.flip(where[0][1])
    assert (match.player, match.next_player) == (0, 0)
    assert game.current == 0 and game.player_pairs == [1, 0, 0]

    game.flip(where[1][0])
    miss = game.flip(where[2][0])
    assert (miss.player, miss.next_player) == (0, 1)
    assert game.current == 1

    first = game.flip(where[1][1])  # resolves the wrong pair; now player 2's move
    assert first.player == 1 and first.hidden
    game.flip(where[1][0])
    assert game.player_pairs == [1, 1, 0]
    assert game.player_points == [100, 100, 0]


def test_turn_wraps_around_and_streak_resets_per_turn():
    game = make_game(pairs=4, players=2)
    where = pair_indices(game)
    for expected_next in (1, 0, 1):
        game.flip(where[0][0])
        game.flip(where[1][0])
        assert game.current == expected_next
        game.resolve_mismatch()
    game.flip(where[0][0])
    result = game.flip(where[0][1])
    assert result.player == 1 and result.points == 100  # no multiplier carried over


def test_leaders_handles_ties():
    game = make_game(pairs=3, players=2)
    where = pair_indices(game)
    game.flip(where[0][0])
    game.flip(where[0][1])
    assert game.leaders == [0]
    game.flip(where[1][0])
    game.flip(where[2][0])  # player 0 misses; player 1's turn
    game.flip(where[1][1])
    game.flip(where[1][0])
    assert game.player_pairs == [1, 1]
    assert game.leaders == [0, 1]


def test_solo_game_never_changes_player():
    game = make_game(pairs=3)
    a, b = mismatched_pair(game)
    game.flip(a)
    result = game.flip(b)
    assert (result.player, result.next_player, game.current) == (0, 0, 0)


def test_rejects_zero_players():
    with pytest.raises(ValueError):
        MemoryGame([1, 2], players=0)
