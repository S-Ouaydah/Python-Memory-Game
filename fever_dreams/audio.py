"""Procedurally synthesised sound effects (no audio files needed).

Sounds are rendered in pure Python on a background thread at start-up, so the
window appears immediately; anything played before it's ready is skipped.
If no audio device is available the game simply runs silently.
"""

from __future__ import annotations

import math
import random
import threading
from array import array

import pygame

SAMPLE_RATE = 44100

#: Major-scale steps used to raise the match chime with each combo.
COMBO_STEPS = (0, 2, 4, 5, 7, 9, 11, 12)


def _silence(seconds: float) -> list[float]:
    return [0.0] * int(seconds * SAMPLE_RATE)


def _mix(buf: list[float], other: list[float], at: float = 0.0, gain: float = 1.0) -> None:
    start = int(at * SAMPLE_RATE)
    end = min(len(buf), start + len(other))
    for i in range(start, end):
        buf[i] += other[i - start] * gain


def _bell(freq: float, seconds: float, amp: float = 0.5, decay: float = 3.2) -> list[float]:
    """A soft glassy bell: a few inharmonic partials with exponential decay."""
    n = int(seconds * SAMPLE_RATE)
    out = [0.0] * n
    attack = int(0.004 * SAMPLE_RATE)
    for ratio, weight in ((1.0, 1.0), (2.0, 0.32), (3.01, 0.14), (4.18, 0.06)):
        w = math.tau * freq * ratio / SAMPLE_RATE
        k = math.exp(-decay * (1 + ratio * 0.55) / SAMPLE_RATE)
        env = amp * weight
        for i in range(n):
            out[i] += math.sin(w * i) * env
            env *= k
    for i in range(min(attack, n)):
        out[i] *= i / attack
    return out


def _sweep(f0: float, f1: float, seconds: float, amp: float) -> list[float]:
    n = int(seconds * SAMPLE_RATE)
    out = [0.0] * n
    phase = 0.0
    for i in range(n):
        t = i / n
        phase += math.tau * (f0 + (f1 - f0) * t) / SAMPLE_RATE
        env = math.sin(math.pi * min(1.0, t * 3.0)) if t < 1 / 6 else (1 - t) ** 1.6
        out[i] = (math.sin(phase) + 0.25 * math.sin(2 * phase)) * amp * env
    return out


def _noise(seconds: float, amp: float, smooth: float, rng: random.Random, shape: str = "flick") -> list[float]:
    """Filtered noise; ``shape`` is a quick 'flick' or a slow 'swell'."""
    n = int(seconds * SAMPLE_RATE)
    out = [0.0] * n
    low = 0.0
    for i in range(n):
        t = i / n
        low += (rng.uniform(-1, 1) - low) * smooth
        if shape == "flick":
            env = min(1.0, t * 30) * (1 - t) ** 3
        else:
            env = math.sin(math.pi * t) ** 2
        out[i] = low * amp * env
    return out


def _flip(rng: random.Random) -> list[float]:
    buf = _noise(0.09, 0.6, 0.35, rng)
    _mix(buf, _sweep(520, 240, 0.07, 0.12))
    return buf


def _match(step: int) -> list[float]:
    base = 659.25 * 2 ** (COMBO_STEPS[min(step, len(COMBO_STEPS) - 1)] / 12)
    buf = _silence(1.1)
    _mix(buf, _bell(base, 0.9, 0.34))
    _mix(buf, _bell(base * 1.5, 0.95, 0.28), at=0.075)
    _mix(buf, _bell(base * 2.0, 0.6, 0.08), at=0.14)
    return buf


def _miss() -> list[float]:
    buf = _sweep(392, 262, 0.3, 0.2)
    _mix(buf, _sweep(196, 131, 0.3, 0.08))
    return buf


def _win() -> list[float]:
    buf = _silence(2.4)
    notes = (523.25, 659.25, 783.99, 1046.5, 1318.5)
    for i, freq in enumerate(notes):
        _mix(buf, _bell(freq, 1.6, 0.26, decay=2.0), at=i * 0.11)
    for i, freq in enumerate((2093.0, 2637.0, 3136.0)):
        _mix(buf, _bell(freq, 0.8, 0.05, decay=3.0), at=0.6 + i * 0.07)
    return buf


def _glimpse(rng: random.Random) -> list[float]:
    buf = _noise(0.9, 0.22, 0.08, rng, shape="swell")
    for i, freq in enumerate((1174.7, 1568.0, 1760.0, 2349.3)):
        _mix(buf, _bell(freq, 0.6, 0.07, decay=4.0), at=0.05 + i * 0.06)
    return buf


def _star(index: int) -> list[float]:
    return _bell(880.0 * 2 ** ((index * 4) / 12), 0.7, 0.22, decay=3.5)


def _click() -> list[float]:
    return _bell(1318.5, 0.08, 0.14, decay=40)


def _hover() -> list[float]:
    return _bell(1760.0, 0.05, 0.035, decay=60)


def _deal(rng: random.Random) -> list[float]:
    return _noise(0.7, 0.35, 0.12, rng, shape="swell")


class Audio:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.available = False
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(SAMPLE_RATE, -16, 2, 512)
            pygame.mixer.set_num_channels(24)
        except pygame.error:
            return
        init = pygame.mixer.get_init()
        if not init or init[1] != -16:  # samples are rendered as signed 16-bit
            return
        self.available = True
        self._rate, _fmt, self._channels = init
        threading.Thread(target=self._build, name="sfx-synth", daemon=True).start()

    def _build(self) -> None:
        rng = random.Random(7)
        recipes = {
            "flip": lambda: _flip(rng),
            "miss": _miss,
            "click": _click,
            "hover": _hover,
            "deal": lambda: _deal(rng),
            "glimpse": lambda: _glimpse(rng),
            **{f"match{i}": (lambda i=i: _match(i)) for i in range(len(COMBO_STEPS))},
            "win": _win,
            **{f"star{i}": (lambda i=i: _star(i)) for i in range(3)},
        }
        for name, recipe in recipes.items():
            try:
                self._sounds[name] = self._to_sound(recipe())
            except (pygame.error, ValueError):  # mixer closed during shutdown, etc.
                return

    def _to_sound(self, samples: list[float]) -> pygame.mixer.Sound:
        if self._rate != SAMPLE_RATE:  # resample by nearest neighbour if needed
            ratio = SAMPLE_RATE / self._rate
            samples = [samples[int(i * ratio)] for i in range(int(len(samples) / ratio))]
        pcm = array("h", (int(max(-1.0, min(1.0, s)) * 32000) for s in samples))
        if self._channels > 1:
            interleaved = array("h", bytes(len(pcm) * 2 * self._channels))
            for c in range(self._channels):
                interleaved[c :: self._channels] = pcm
            pcm = interleaved
        return pygame.mixer.Sound(buffer=pcm.tobytes())

    def play(self, name: str, volume: float = 1.0) -> None:
        if not (self.enabled and self.available):
            return
        sound = self._sounds.get(name)
        if sound is not None:
            channel = sound.play()
            if channel is not None:
                channel.set_volume(volume)

    def play_match(self, streak: int) -> None:
        self.play(f"match{max(0, min(streak - 1, len(COMBO_STEPS) - 1))}")
