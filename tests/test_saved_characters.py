import uuid

from data import saved_characters
from data.models import Character


def test_saved_characters_init(tmp_path):
    saved_characters.SAVED_CHARS = None
    (tmp_path / 'char.yaml').write_text('{"name": "Test"}', encoding="utf-8")
    saved_characters.init(tmp_path)
    assert saved_characters.SAVED_CHARS is not None
    assert saved_characters.SAVED_CHARS.char_list


def test_saved_characters_init_skips_broken_files(tmp_path):
    saved_characters.SAVED_CHARS = None
    (tmp_path / 'good.yaml').write_text('{"name": "Good"}', encoding="utf-8")
    (tmp_path / 'broken.yaml').write_text('name: [unclosed', encoding="utf-8")
    (tmp_path / 'invalid.yaml').write_text('level: 999', encoding="utf-8")
    saved_characters.init(tmp_path)
    assert [c.name for c in saved_characters.SAVED_CHARS.char_list] == ["Good"]
    assert sorted(p.name for p in saved_characters.SAVED_CHARS.failed_files) == ["broken.yaml", "invalid.yaml"]


def test_saved_characters_init_reads_legacy_tags(tmp_path):
    saved_characters.SAVED_CHARS = None
    char_id = uuid.uuid4()
    legacy = (
        f"id: !!python/object:uuid.UUID\n"
        f"  int: {char_id.int}\n"
        f"name: Old\n"
        f"dexterity:\n"
        f"  name: !!python/object/apply:data.models.attributes.AttributeName\n"
        f"  - dexterity\n"
        f"  base: 10\n"
        f"  current: 10\n"
    )
    (tmp_path / 'old.yaml').write_text(legacy, encoding="utf-8")
    saved_characters.init(tmp_path)
    [char] = saved_characters.SAVED_CHARS.char_list
    assert char.id == char_id
    assert char.dexterity.base == 10


def test_saved_characters_refuses_arbitrary_python_objects(tmp_path):
    saved_characters.SAVED_CHARS = None
    marker = tmp_path / "pwned"
    evil = f"name: !!python/object/apply:pathlib.Path.touch [!!python/object/apply:pathlib.Path ['{marker.as_posix()}']]\n"
    (tmp_path / 'evil.yaml').write_text(evil, encoding="utf-8")
    saved_characters.init(tmp_path)
    assert not marker.exists()
    assert saved_characters.SAVED_CHARS.char_list == []


def test_upsert_stores_a_copy_and_replaces_by_id():
    saved = saved_characters.SavedChars(char_list=[])
    char = Character(name="Hana", level=5)
    saved.upsert(char)
    char.level = 6
    assert saved.char_list[0].level == 5
    saved.upsert(char)
    assert len(saved.char_list) == 1
    assert saved.char_list[0].level == 6
    saved.remove(char.id)
    assert saved.char_list == []
