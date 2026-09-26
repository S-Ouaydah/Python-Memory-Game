"""Pure rules for the pairs-matching game.

Nothing in here touches pygame, so the rules can be unit tested and reasoned
about on their own. The game scene owns a :class:`MemoryGame` and turns the
:class:`FlipResult` values it returns into animation and sound.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto

BASE_PAIR_POINTS = 100
MAX_MULTIPLIER = 3.0
GLIMPSE_COST = 250
TIME_BONUS_PER_SECOND = 10

#: Moves-per-pair ratios needed for three and two stars. With perfect memory
#: the expected cost of clearing a board is roughly 1.6 moves per pair.
THREE_STAR_RATIO = 1.75
TWO_STAR_RATIO = 2.5


class CardState(Enum):
    HIDDEN = auto()
    REVEALED = auto()
    MATCHED = auto()


class Outcome(Enum):
    IGNORED = auto()  # the click had no effect on the board
    FIRST = auto()  # first card of a pair turned over
    MATCH = auto()
    MISMATCH = auto()


@dataclass
class Card:
    face: int
    state: CardState = CardState.HIDDEN


@dataclass(frozen=True)
class FlipResult:
    outcome: Outcome
    index: int
    #: The other card of the pair, for MATCH and MISMATCH.
    partner: int | None = None
    #: Cards turned face down as a side effect (an unresolved mismatch).
    hidden: tuple[int, ...] = ()
    points: int = 0
    streak: int = 0
    finished: bool = False
    #: Who turned the card over.
    player: int = 0
    #: Whose turn it is now (differs from ``player`` after a miss).
    next_player: int = 0


@dataclass(frozen=True)
class FinalScore:
    match_points: int
    time_bonus: int
    glimpse_penalty: int
    total: int
    stars: int


def streak_multiplier(streak: int) -> float:
    """1x for a lone match, +0.5x for each consecutive match, capped at 3x."""
    if streak <= 1:
        return 1.0
    return min(MAX_MULTIPLIER, 1.0 + 0.5 * (streak - 1))


def star_rating(moves: int, pairs: int) -> int:
    """Rate a finished board from one to three stars by moves per pair."""
    if pairs <= 0:
        return 0
    if moves <= math.ceil(pairs * THREE_STAR_RATIO):
        return 3
    if moves <= math.ceil(pairs * TWO_STAR_RATIO):
        return 2
    return 1


class MemoryGame:
    """A shuffled board of card pairs plus the running score for one round.

    A *move* is turning over two cards. When they differ, the pair stays face
    up (``pending``) until :meth:`resolve_mismatch` is called or the player
    flips another card, which resolves it automatically. The player never
    has to wait out a wrong guess.

    With several ``players`` they take turns: a match earns another go, a
    miss passes the turn to the next player.
    """

    def __init__(
        self,
        faces: Sequence[int],
        rng: random.Random | None = None,
        glimpses: int = 1,
        players: int = 1,
    ) -> None:
        if not faces:
            raise ValueError("a game needs at least one pair")
        if len(set(faces)) != len(faces):
            raise ValueError("faces must be unique")
        if players < 1:
            raise ValueError("a game needs at least one player")
        self.players = players
        self.current = 0
        self.player_pairs = [0] * players
        self.player_points = [0] * players
        deck = [face for face in faces for _ in range(2)]
        (rng or random.Random()).shuffle(deck)
        self.cards = [Card(face) for face in deck]
        self.pairs = len(faces)
        self.moves = 0
        self.matches = 0
        self.misses = 0
        self.streak = 0
        self.best_streak = 0
        self.match_points = 0
        self.glimpses_left = glimpses
        self.glimpses_used = 0
        self._first: int | None = None
        self._pending: tuple[int, int] | None = None

    # -- state -------------------------------------------------------------

    @property
    def finished(self) -> bool:
        return self.matches == self.pairs

    @property
    def leaders(self) -> list[int]:
        """Players holding the most pairs (several on a tie)."""
        best = max(self.player_pairs)
        return [i for i, pairs in enumerate(self.player_pairs) if pairs == best]

    @property
    def first(self) -> int | None:
        """The index of the lone face-up card waiting for its partner."""
        return self._first

    @property
    def pending(self) -> tuple[int, int] | None:
        """A mismatched pair that is still face up."""
        return self._pending

    @property
    def score(self) -> int:
        return max(0, self.match_points - self.glimpses_used * GLIMPSE_COST)

    @property
    def accuracy(self) -> float:
        """Share of moves that found a pair (0.0 before the first move)."""
        return self.matches / self.moves if self.moves else 0.0

    @property
    def multiplier(self) -> float:
        """The multiplier the *next* match would earn."""
        return streak_multiplier(self.streak + 1)

    def is_selectable(self, index: int) -> bool:
        return not self.finished and self.cards[index].state is CardState.HIDDEN

    # -- actions -----------------------------------------------------------

    def flip(self, index: int) -> FlipResult:
        if not 0 <= index < len(self.cards):
            raise IndexError(f"no card at index {index}")
        if self.finished:
            return FlipResult(Outcome.IGNORED, index)

        # Clicking one of a face-up wrong pair just dismisses the pair.
        dismissing = self._pending is not None and index in self._pending
        hidden = self.resolve_mismatch()
        card = self.cards[index]
        player = self.current
        if dismissing or card.state is not CardState.HIDDEN:
            return FlipResult(Outcome.IGNORED, index, hidden=hidden, player=player, next_player=player)

        card.state = CardState.REVEALED
        if self._first is None:
            self._first = index
            return FlipResult(Outcome.FIRST, index, hidden=hidden, player=player, next_player=player)

        partner, self._first = self._first, None
        self.moves += 1
        other = self.cards[partner]
        if other.face == card.face:
            card.state = other.state = CardState.MATCHED
            self.matches += 1
            self.streak += 1
            self.best_streak = max(self.best_streak, self.streak)
            points = round(BASE_PAIR_POINTS * streak_multiplier(self.streak))
            self.match_points += points
            self.player_pairs[player] += 1
            self.player_points[player] += points
            return FlipResult(
                Outcome.MATCH,
                index,
                partner,
                hidden,
                points=points,
                streak=self.streak,
                finished=self.finished,
                player=player,
                next_player=player,
            )

        self.misses += 1
        self.streak = 0
        self._pending = (partner, index)
        self.current = (player + 1) % self.players
        return FlipResult(Outcome.MISMATCH, index, partner, hidden, player=player, next_player=self.current)

    def resolve_mismatch(self) -> tuple[int, ...]:
        """Turn a pending mismatched pair face down; returns their indices."""
        if self._pending is None:
            return ()
        hidden, self._pending = self._pending, None
        for i in hidden:
            self.cards[i].state = CardState.HIDDEN
        return hidden

    def use_glimpse(self) -> bool:
        """Spend a glimpse (a brief look at every card). False if none left."""
        if self.glimpses_left <= 0 or self.finished:
            return False
        self.glimpses_left -= 1
        self.glimpses_used += 1
        return True

    def final_score(self, elapsed: float, par_time: float) -> FinalScore:
        time_bonus = 0
        if self.finished:
            time_bonus = int(max(0.0, par_time - elapsed) * TIME_BONUS_PER_SECOND)
        penalty = self.glimpses_used * GLIMPSE_COST
        total = max(0, self.match_points + time_bonus - penalty)
        stars = star_rating(self.moves, self.pairs) if self.finished else 0
        return FinalScore(self.match_points, time_bonus, penalty, total, stars)
