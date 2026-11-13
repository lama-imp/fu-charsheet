from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from data.models import Character
from data.persistence import load_yaml


logger = logging.getLogger(__name__)

SAVED_CHARS: SavedChars | None = None


@dataclass(frozen=True)
class SavedChars:
    char_list: list[Character]
    # Files that could not be read, so the UI can tell the user about them.
    failed_files: list[Path] = field(default_factory=list)

    def upsert(self, character: Character) -> None:
        """Record `character` as saved, replacing an older entry with the same id.

        A copy is stored, so later (unsaved) edits to `character` don't show up here.
        """
        saved = character.model_copy(deep=True)
        for i, existing in enumerate(self.char_list):
            if existing.id == character.id:
                self.char_list[i] = saved
                return
        self.char_list.append(saved)

    def remove(self, char_id: uuid.UUID) -> None:
        self.char_list[:] = [c for c in self.char_list if c.id != char_id]


def init(saved_chars_directory: Path) -> None:
    global SAVED_CHARS
    if SAVED_CHARS is not None:
        return

    char_list = []
    failed_files = []
    for yaml_file in sorted(saved_chars_directory.glob('*.yaml')):
        try:
            raw_char = load_yaml(yaml_file)
            char_list.append(Character(**dict(raw_char)))
        except Exception:
            logger.exception("Could not load saved character from %s", yaml_file)
            failed_files.append(yaml_file)

    SAVED_CHARS = SavedChars(
        char_list=char_list,
        failed_files=failed_files,
    )


if __name__ == "__main__":
    init(Path("fabula_charsheet/characters"))
    print(SAVED_CHARS)
