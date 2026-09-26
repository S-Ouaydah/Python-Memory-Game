import json

from fever_dreams.storage import Record, SaveData, default_data_dir


def test_missing_file_gives_defaults(tmp_path):
    save = SaveData.load(tmp_path / "nope.json")
    assert save.settings.sound is True
    assert save.records == {}


def test_round_trip(tmp_path):
    path = tmp_path / "sub" / "save.json"
    save = SaveData.load(path)
    save.settings.sound = False
    save.settings.last_difficulty = "fever"
    save.register_win("fever", score=1234, time=99.5, moves=40, stars=2)
    assert save.save()

    loaded = SaveData.load(path)
    assert loaded.settings.sound is False
    assert loaded.settings.last_difficulty == "fever"
    assert loaded.record("fever") == Record(wins=1, best_score=1234, best_time=99.5, best_moves=40, best_stars=2)


def test_corrupt_file_is_ignored(tmp_path):
    path = tmp_path / "save.json"
    path.write_text("{not json", encoding="utf-8")
    assert SaveData.load(path).records == {}
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert SaveData.load(path).records == {}


def test_mistyped_values_fall_back_to_defaults(tmp_path):
    path = tmp_path / "save.json"
    path.write_text(
        json.dumps(
            {
                "settings": {"sound": "yes", "ambient": False, "bogus": 1},
                "records": {"drift": {"wins": "3", "best_score": 500}},
            }
        ),
        encoding="utf-8",
    )
    save = SaveData.load(path)
    assert save.settings.sound is True
    assert save.settings.ambient is False
    assert save.record("drift").wins == 0
    assert save.record("drift").best_score == 500


def test_new_bests_only_after_first_win(tmp_path):
    save = SaveData.load(tmp_path / "save.json")
    first = save.register_win("serene", score=500, time=60, moves=12, stars=2)
    assert not first.any
    worse = save.register_win("serene", score=400, time=70, moves=11, stars=1)
    assert (worse.score, worse.time, worse.moves) == (False, False, True)
    rec = save.record("serene")
    assert (rec.wins, rec.best_score, rec.best_time, rec.best_moves, rec.best_stars) == (
        2,
        500,
        60,
        11,
        2,
    )


def test_unwritable_location_does_not_raise(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    save = SaveData.load(blocker / "save.json")
    assert save.save() is False


def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("FEVER_DREAMS_HOME", str(tmp_path))
    assert default_data_dir() == tmp_path
