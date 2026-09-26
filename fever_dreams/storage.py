"""Settings and personal records, persisted as JSON in the user's data folder."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

APP_DIR_NAME = "fever-dreams"
SAVE_VERSION = 1


def default_data_dir() -> Path:
    """Per-user data folder; ``FEVER_DREAMS_HOME`` overrides it."""
    override = os.environ.get("FEVER_DREAMS_HOME")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_DIR_NAME


@dataclass
class Settings:
    sound: bool = True
    fullscreen: bool = False
    #: Drifting petals and motes in the background.
    ambient: bool = True
    last_difficulty: str = "serene"


@dataclass
class Record:
    wins: int = 0
    best_score: int | None = None
    best_time: float | None = None
    best_moves: int | None = None
    best_stars: int = 0


@dataclass(frozen=True)
class NewBests:
    score: bool = False
    time: bool = False
    moves: bool = False

    @property
    def any(self) -> bool:
        return self.score or self.time or self.moves


def _from_dict(cls, data):
    """Build a dataclass from ``data``, ignoring unknown or mistyped keys."""
    obj = cls()
    if not isinstance(data, dict):
        return obj
    for f in fields(cls):
        if f.name not in data:
            continue
        value, default = data[f.name], getattr(obj, f.name)
        if isinstance(default, bool):
            ok = isinstance(value, bool)
        elif isinstance(default, int) and not isinstance(default, bool):
            ok = isinstance(value, int) and not isinstance(value, bool)
        elif default is None:
            ok = value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))
        else:
            ok = isinstance(value, type(default))
        if ok:
            setattr(obj, f.name, value)
    return obj


@dataclass
class SaveData:
    path: Path
    settings: Settings = field(default_factory=Settings)
    records: dict[str, Record] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> SaveData:
        """Read the save file; a missing or corrupt file yields defaults."""
        path = path or default_data_dir() / "save.json"
        save = cls(path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return save
        if not isinstance(raw, dict):
            return save
        save.settings = _from_dict(Settings, raw.get("settings"))
        records = raw.get("records")
        if isinstance(records, dict):
            save.records = {str(k): _from_dict(Record, v) for k, v in records.items()}
        return save

    def save(self) -> bool:
        """Write atomically. Returns False (and keeps playing) on I/O errors."""
        payload = {
            "version": SAVE_VERSION,
            "settings": asdict(self.settings),
            "records": {k: asdict(v) for k, v in self.records.items()},
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".save-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2)
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        except OSError:
            return False
        return True

    def record(self, key: str) -> Record:
        return self.records.get(key) or Record()

    def register_win(self, key: str, score: int, time: float, moves: int, stars: int) -> NewBests:
        rec = self.records.setdefault(key, Record())
        first = rec.wins == 0
        bests = NewBests(
            score=not first and (rec.best_score is None or score > rec.best_score),
            time=not first and (rec.best_time is None or time < rec.best_time),
            moves=not first and (rec.best_moves is None or moves < rec.best_moves),
        )
        rec.wins += 1
        if rec.best_score is None or score > rec.best_score:
            rec.best_score = score
        if rec.best_time is None or time < rec.best_time:
            rec.best_time = time
        if rec.best_moves is None or moves < rec.best_moves:
            rec.best_moves = moves
        rec.best_stars = max(rec.best_stars, stars)
        return bests

    def reset_records(self) -> None:
        self.records.clear()
