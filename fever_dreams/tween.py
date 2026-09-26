"""Easing curves and small animation helpers."""

from __future__ import annotations

import math


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(a, b, t: float) -> tuple[int, ...]:
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def approach(current: float, target: float, rate: float, dt: float) -> float:
    """Frame-rate independent exponential smoothing towards ``target``."""
    return target + (current - target) * math.exp(-rate * dt)


def step_toward(current: float, target: float, amount: float) -> float:
    """Move linearly towards ``target`` by at most ``amount``."""
    if current < target:
        return min(target, current + amount)
    return max(target, current - amount)


def ease_out_cubic(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    t = clamp(t)
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_in_out_sine(t: float) -> float:
    return -(math.cos(math.pi * clamp(t)) - 1) / 2


def ease_out_back(t: float, overshoot: float = 1.70158) -> float:
    t = clamp(t)
    c3 = overshoot + 1
    return 1 + c3 * (t - 1) ** 3 + overshoot * (t - 1) ** 2


def ease_out_elastic(t: float) -> float:
    t = clamp(t)
    if t in (0.0, 1.0):
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi) / 3) + 1


def bump(t: float) -> float:
    """0 → 1 → 0 over ``t`` in [0, 1] (half a sine wave)."""
    return math.sin(math.pi * clamp(t))


class Timer:
    """Counts up to ``duration``; ``progress`` runs from 0 to 1."""

    __slots__ = ("duration", "elapsed")

    def __init__(self, duration: float, delay: float = 0.0) -> None:
        self.duration = max(duration, 1e-6)
        self.elapsed = -delay

    def update(self, dt: float) -> None:
        self.elapsed += dt

    @property
    def progress(self) -> float:
        return clamp(self.elapsed / self.duration)

    @property
    def done(self) -> bool:
        return self.elapsed >= self.duration
