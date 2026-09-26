"""End-to-end smoke tests: drive the real app headlessly with synthetic input."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
import pytest  # noqa: E402

from fever_dreams.app import App  # noqa: E402
from fever_dreams.config import DIFFICULTY_BY_KEY  # noqa: E402
from fever_dreams.logic import CardState  # noqa: E402
from fever_dreams.scenes.game import GameScene, PauseModal, Phase, ResultsModal  # noqa: E402
from fever_dreams.scenes.menu import MenuScene  # noqa: E402
from fever_dreams.storage import SaveData  # noqa: E402

DT = 1 / 60


@pytest.fixture
def app(tmp_path):
    app = App(size=(1280, 800), fullscreen=False, seed=42, save=SaveData(path=tmp_path / "save.json"))
    yield app
    app.shutdown()


def run(app, seconds, events=()):
    app.step(DT, list(events))
    for _ in range(int(seconds / DT)):
        app.step(DT, [])


def click(pos):
    return [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1),
        pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1),
    ]


def key(k):
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)


def start_game(app, difficulty="serene"):
    run(app, 1.0, [key(pygame.K_1 + list(DIFFICULTY_BY_KEY).index(difficulty))])
    scene = app.scene
    assert isinstance(scene, GameScene)
    assert scene.difficulty.key == difficulty
    run(app, 0.1, click((5, app.size[1] - 5)))  # a click skips the deal
    assert scene.phase is Phase.PLAYING
    return scene


def pairs_of(game):
    where = {}
    for i, card in enumerate(game.cards):
        where.setdefault(card.face, []).append(i)
    return list(where.values())


def test_menu_renders_and_responds(app):
    run(app, 1.0)
    assert isinstance(app.scene, MenuScene)
    app.scene.open_help()
    run(app, 0.5)
    run(app, 0.5, [key(pygame.K_ESCAPE)])
    assert app.scene.modal is None


def test_full_game_by_mouse_records_a_win(app):
    scene = start_game(app, "serene")
    game = scene.game
    pairs = pairs_of(game)

    # One wrong guess first; flipping a third card resolves it straight away.
    a, b = pairs[0][0], pairs[1][0]
    run(app, 0.1, click(scene.sprites[a].rect.center))
    run(app, 0.1, click(scene.sprites[b].rect.center))
    assert game.pending == (a, b)
    run(app, 0.1, click(scene.sprites[pairs[2][0]].rect.center))
    assert game.pending is None and game.first == pairs[2][0]
    run(app, 0.1, click(scene.sprites[pairs[2][1]].rect.center))

    for i, j in pairs:
        if game.cards[i].state is CardState.MATCHED:
            continue
        run(app, 0.1, click(scene.sprites[i].rect.center))
        run(app, 0.1, click(scene.sprites[j].rect.center))
    run(app, 0.6)
    assert game.finished
    assert scene.phase in (Phase.CELEBRATING, Phase.RESULTS)
    run(app, 2.5)
    assert isinstance(scene.modal, ResultsModal)

    record = app.save.record("serene")
    assert record.wins == 1
    assert record.best_moves == game.moves == 7
    assert record.best_score == scene.final.total > 0
    assert SaveData.load(app.save.path).record("serene").wins == 1

    run(app, 1.0, [key(pygame.K_r)])  # R on the results screen plays again
    assert isinstance(app.scene, GameScene) and app.scene is not scene


def test_keyboard_play_and_pause(app):
    scene = start_game(app, "drift")
    game = scene.game
    run(app, 0.1, [key(pygame.K_RIGHT)])  # first arrow shows the focus ring
    run(app, 0.1, [key(pygame.K_RIGHT)])
    assert scene.focus_index is not None
    run(app, 0.2, [key(pygame.K_SPACE)])
    assert game.first == scene.focus_index
    assert scene.clock_running

    run(app, 0.3, [key(pygame.K_ESCAPE)])
    assert isinstance(scene.modal, PauseModal)
    frozen = scene.elapsed
    run(app, 1.0)
    assert scene.elapsed == frozen
    run(app, 0.5, [key(pygame.K_ESCAPE)])
    assert scene.modal is None
    run(app, 0.5)
    assert scene.elapsed > frozen


def test_focus_loss_pauses_a_running_game(app):
    scene = start_game(app)
    run(app, 0.1, click(scene.sprites[0].rect.center))
    run(app, 0.1, [pygame.event.Event(pygame.WINDOWFOCUSLOST)])
    assert isinstance(scene.modal, PauseModal)


def test_glimpse_is_single_use(app):
    scene = start_game(app)
    run(app, 0.1, [key(pygame.K_g)])
    assert scene.phase is Phase.GLIMPSE
    assert all(s.face_up for s in scene.sprites)
    run(app, 2.0)
    assert scene.phase is Phase.PLAYING
    assert not any(s.face_up for s in scene.sprites)
    run(app, 0.1, [key(pygame.K_g)])
    assert scene.phase is Phase.PLAYING
    assert scene.game.glimpses_used == 1


def test_resize_relayouts_cards_inside_the_window(app):
    scene = start_game(app, "fever")
    app.screen = pygame.display.set_mode((1000, 700), pygame.RESIZABLE)
    run(app, 0.2, [pygame.event.Event(pygame.VIDEORESIZE, size=(1000, 700), w=1000, h=700)])
    window = pygame.Rect(0, 0, 1000, 700)
    assert all(window.contains(s.rect) for s in scene.sprites)
    assert scene.hud.right <= 1000


def test_back_to_menu_from_pause(app):
    scene = start_game(app)
    run(app, 0.4, [key(pygame.K_ESCAPE)])
    scene.modal.menu.activate()
    run(app, 1.0)
    assert isinstance(app.scene, MenuScene)


def test_hot_seat_turns_colours_and_results(app):
    app.save.settings.players = 2
    scene = start_game(app, "serene")
    assert scene.multiplayer and not scene.glimpse_button.visible
    game = scene.game
    pairs = pairs_of(game)

    # Player 1 matches and keeps the turn, then misses and hands over.
    run(app, 0.1, click(scene.sprites[pairs[0][0]].rect.center))
    run(app, 0.6, click(scene.sprites[pairs[0][1]].rect.center))
    assert game.current == 0
    assert scene.sprites[pairs[0][0]].match_color == scene.player_color(0)
    run(app, 0.1, click(scene.sprites[pairs[1][0]].rect.center))
    run(app, 0.6, click(scene.sprites[pairs[2][0]].rect.center))
    assert game.current == 1
    assert scene.banner_player == 1

    # Player 2 clears the rest of the board (starting away from the face-up
    # wrong pair, since clicking one of those only dismisses it).
    for i, j in pairs[1:]:
        run(app, 0.1, click(scene.sprites[j].rect.center))
        run(app, 0.1, click(scene.sprites[i].rect.center))
    run(app, 3.0)
    assert game.player_pairs == [1, 5] and game.leaders == [1]
    assert scene.sprites[pairs[3][0]].match_color == scene.player_color(1)
    assert isinstance(scene.modal, ResultsModal)
    assert scene.modal.again.label == "Rematch"
    assert app.save.record("serene").wins == 0  # hot-seat games don't touch solo records

    run(app, 1.0, [key(pygame.K_r)])
    assert isinstance(app.scene, GameScene) and app.scene.players == 2


def test_player_chips_on_the_menu(app):
    run(app, 1.5)
    menu = app.scene
    run(app, 0.1, click(menu.chips[2].rect.center))
    assert app.save.settings.players == 3
    run(app, 1.0, [key(pygame.K_2)])
    assert isinstance(app.scene, GameScene) and app.scene.players == 3


def test_fifty_pair_board_uses_distinct_variant_faces(app):
    scene = start_game(app, "delirium")
    faces = [c.face for c in scene.game.cards]
    assert len(faces) == 100 and len(set(faces)) == 50
    assert max(faces) >= app.art.count  # mirrored / close-up variants in play
    window = pygame.Rect(0, 0, *app.size)
    assert all(window.contains(s.rect) for s in scene.sprites)
    run(app, 0.3, click(scene.sprites[99].rect.center))
    assert scene.game.first == 99
