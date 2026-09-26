"""Regenerate the README screenshots and preview animation (runs headlessly).

    python tools/capture_screenshots.py [output_dir]

Plays a scripted game with a fixed seed and saves PNGs of each screen plus an
animated WebP of the opening moments. Requires Pillow for the animation.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame  # noqa: E402

from fever_dreams.app import App  # noqa: E402
from fever_dreams.config import DIFFICULTY_BY_KEY  # noqa: E402
from fever_dreams.logic import CardState  # noqa: E402
from fever_dreams.scenes.game import GameScene  # noqa: E402
from fever_dreams.scenes.menu import MenuScene  # noqa: E402
from fever_dreams.storage import SaveData  # noqa: E402

DT = 1 / 60
SIZE = (1280, 800)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/screenshots")
    out.mkdir(parents=True, exist_ok=True)
    save = SaveData(path=Path(tempfile.mkdtemp()) / "save.json")
    app = App(size=SIZE, fullscreen=False, seed=11, save=save)
    frames: list[pygame.Surface] = []
    recording = {"on": False, "tick": 0}

    def run(seconds: float) -> None:
        for _ in range(max(1, int(seconds / DT))):
            app.step(DT, [])
            if recording["on"]:
                recording["tick"] += 1
                if recording["tick"] % 3 == 0:  # 20 fps
                    frames.append(pygame.transform.smoothscale(app.screen, (800, 500)))

    def shot(name: str) -> None:
        pygame.image.save(app.screen, str(out / f"{name}.png"))
        print("saved", out / f"{name}.png")

    def pairs(scene: GameScene) -> list[list[int]]:
        where: dict[int, list[int]] = {}
        for i, card in enumerate(scene.game.cards):
            where.setdefault(card.face, []).append(i)
        return list(where.values())

    # A previous win, so the menu shows a record.
    save.register_win("serene", 1840, 38.0, 9, 3)

    run(2.6)
    shot("menu")

    app.switch(lambda: GameScene(app, DIFFICULTY_BY_KEY["drift"]))
    recording["on"] = True
    run(2.4)
    scene = app.scene
    p = pairs(scene)
    for face in p[:3]:
        scene.select(face[0])
        run(0.35)
        scene.select(face[1])
        run(0.7)
    scene.select(p[3][0])
    run(0.35)
    scene.select(p[4][0])
    run(0.9)
    recording["on"] = False
    run(0.6)
    scene.select(p[5][0])
    run(0.6)
    shot("game")

    scene.pause()
    run(0.6)
    shot("pause")
    scene.modal.close()
    run(0.5)

    for face in p[3:]:
        if scene.game.cards[face[0]].state is not CardState.MATCHED:
            scene.select(face[0])
            run(0.1)
            scene.select(face[1])
            run(0.45)
    run(3.2)
    shot("results")

    app.switch(lambda: GameScene(app, DIFFICULTY_BY_KEY["fever"]))
    run(3.0)
    scene = app.scene
    p = pairs(scene)
    for face in p[:5]:
        scene.select(face[0])
        run(0.1)
        scene.select(face[1])
        run(0.45)
    run(1.5)
    shot("fever")

    app.switch(lambda: GameScene(app, DIFFICULTY_BY_KEY["delirium"]))
    run(3.2)
    scene = app.scene
    p = pairs(scene)
    for face in p[:8]:
        scene.select(face[0])
        run(0.1)
        scene.select(face[1])
        run(0.45)
    scene.select(p[9][0])
    run(1.0)
    shot("delirium")

    # Hot-seat: three players on Reverie.
    app.save.settings.players = 3
    app.switch(lambda: MenuScene(app, intro=False))
    run(1.2)
    shot("menu-players")
    app.switch(lambda: GameScene(app, DIFFICULTY_BY_KEY["reverie"], 3))
    run(3.0)
    scene = app.scene
    p = pairs(scene)
    # (first pair, second pair): equal means a match, otherwise a miss.
    for a, b in [(0, 0), (1, 2), (3, 3), (4, 4), (5, 6), (7, 7)]:
        scene.select(p[a][0])
        run(0.35)
        scene.select(p[b][1] if a == b else p[b][0])
        run(0.9 if a == b else 1.7)
    shot("multiplayer")
    for face in p:
        if scene.game.cards[face[0]].state is not CardState.MATCHED:
            scene.select(face[1])
            run(0.1)
            scene.select(face[0])
            run(0.45)
    run(3.4)
    shot("multiplayer-results")
    app.save.settings.players = 1

    app.switch(lambda: MenuScene(app, intro=False))
    run(1.0)
    app.scene.open_help()
    run(0.8)
    shot("help")

    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed; skipping preview.webp")
    else:
        images = [Image.frombytes("RGB", f.get_size(), pygame.image.tobytes(f, "RGB")) for f in frames]
        images[0].save(
            out / "preview.webp", save_all=True, append_images=images[1:], duration=50, loop=0, quality=72, method=6
        )
        print("saved", out / "preview.webp", f"({len(images)} frames)")
    app.shutdown()


if __name__ == "__main__":
    main()
