"""Entry point: ``python -m fever_dreams`` (or the ``fever-dreams`` command)."""

from __future__ import annotations

import argparse
import os


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fever-dreams", description="A memory game of drifting blossoms.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fullscreen", action="store_true", default=None, help="start in fullscreen")
    mode.add_argument("--windowed", dest="fullscreen", action="store_false", help="start in a window")
    parser.add_argument("--seed", type=int, help="seed the shuffle, for reproducible boards")
    args = parser.parse_args(argv)

    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    from .app import App

    App(fullscreen=args.fullscreen, seed=args.seed).run()


if __name__ == "__main__":
    main()
