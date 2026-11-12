import types

import pytest
import yaml

from data.models import Character


@pytest.fixture(autouse=True)
def isolated_save_directories(monkeypatch, tmp_path):
    chars_dir = tmp_path / "characters"
    img_dir = tmp_path / "characters" / "character_images"
    states_dir = tmp_path / "characters" / "states"
    chars_dir.mkdir(parents=True)
    img_dir.mkdir(parents=True)
    states_dir.mkdir(parents=True)
    monkeypatch.setattr("pages.controller.SAVED_CHARS_DIRECTORY", chars_dir)
    monkeypatch.setattr("pages.controller.SAVED_CHARS_IMG_DIRECTORY", img_dir)
    monkeypatch.setattr("pages.controller.SAVED_STATES_DIRECTORY", states_dir)
    return types.SimpleNamespace(chars=chars_dir, images=img_dir, states=states_dir)


def test_dump_character_writes_expected_file(controller, isolated_save_directories):
    controller.character.name = "Alice"
    controller.dump_character()
    expected = isolated_save_directories.chars / f"Alice.{controller.character.id}.character.yaml"
    assert expected.exists()


def test_dump_character_round_trips_via_yaml(controller, isolated_save_directories):
    controller.character.name = "Bob"
    controller.character.level = 12
    controller.dump_character()
    saved_path = isolated_save_directories.chars / f"Bob.{controller.character.id}.character.yaml"
    with saved_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)  # plain YAML only, no Python object tags
    reloaded = Character(**raw)
    assert reloaded.name == "Bob"
    assert reloaded.level == 12
    assert reloaded.id == controller.character.id


def test_dump_character_removes_stale_files_for_same_id(controller, isolated_save_directories):
    controller.character.name = "Old Name"
    controller.dump_character()
    controller.character.name = "New Name"
    controller.dump_character()
    matches = list(isolated_save_directories.chars.glob(f"*.{controller.character.id}.character.yaml"))
    assert len(matches) == 1
    assert matches[0].name == f"New Name.{controller.character.id}.character.yaml"


def test_dump_state_writes_expected_file(controller, isolated_save_directories):
    controller.state.minus_hp = 7
    controller.dump_state()
    expected = isolated_save_directories.states / f"{controller.character.id}.yaml"
    assert expected.exists()


def test_load_state_round_trips(controller, isolated_save_directories):
    controller.state.minus_hp = 15
    controller.state.minus_mp = 3
    controller.dump_state()
    controller.state.minus_hp = 0
    controller.state.minus_mp = 0
    controller.load_state()
    assert controller.state.minus_hp == 15
    assert controller.state.minus_mp == 3


def test_load_state_missing_file_resets_state_and_raises(controller):
    controller.state.minus_hp = 99
    with pytest.raises(Exception):
        controller.load_state()
    assert controller.state.minus_hp == 0  # reset to a fresh CharState()


def test_dump_avatar_writes_image_bytes(controller, isolated_save_directories):
    controller.character.name = "Carol"
    image = types.SimpleNamespace(name="avatar.png", getbuffer=lambda: b"PNGDATA")
    controller.dump_avatar(image)
    expected = isolated_save_directories.images / f"Carol.{controller.character.id}.png"
    assert expected.read_bytes() == b"PNGDATA"


def test_dump_avatar_none_is_a_no_op(controller, isolated_save_directories):
    controller.dump_avatar(None)
    assert list(isolated_save_directories.images.iterdir()) == []


def test_dump_avatar_removes_stale_images_for_same_id(controller, isolated_save_directories):
    image_a = types.SimpleNamespace(name="a.png", getbuffer=lambda: b"A")
    image_b = types.SimpleNamespace(name="b.jpg", getbuffer=lambda: b"B")
    controller.character.name = "Dave"
    controller.dump_avatar(image_a)
    controller.dump_avatar(image_b)
    matches = list(isolated_save_directories.images.glob(f"*{controller.character.id}.*"))
    assert len(matches) == 1
    assert matches[0].suffix == ".jpg"


def test_dump_character_handles_non_ascii_text(controller, isolated_save_directories):
    controller.character.name = "Алиса"
    controller.character.identity = "Странствующая колдунья"
    controller.dump_character()
    saved_path = isolated_save_directories.chars / f"Алиса.{controller.character.id}.character.yaml"
    with saved_path.open(encoding="utf-8") as f:
        reloaded = Character(**yaml.safe_load(f))
    assert reloaded.identity == "Странствующая колдунья"


@pytest.mark.parametrize("name", ["a/b:c", "../../escape", "CON", "", "...", 'x<>"|?*'])
def test_dump_character_sanitizes_file_name(controller, isolated_save_directories, name):
    controller.character.name = name
    controller.dump_character()
    matches = list(isolated_save_directories.chars.glob(f"*.{controller.character.id}.character.yaml"))
    assert len(matches) == 1
    assert matches[0].parent == isolated_save_directories.chars
    with matches[0].open(encoding="utf-8") as f:
        assert yaml.safe_load(f)["name"] == name


def test_dump_avatar_sanitizes_file_name(controller, isolated_save_directories):
    controller.character.name = "../a/b:c"
    image = types.SimpleNamespace(name="avatar.png", getbuffer=lambda: b"PNGDATA")
    controller.dump_avatar(image)
    matches = list(isolated_save_directories.images.glob(f"*{controller.character.id}.png"))
    assert len(matches) == 1
    assert matches[0].parent == isolated_save_directories.images


def test_failed_save_keeps_previous_file(controller, isolated_save_directories, monkeypatch):
    controller.character.name = "Eve"
    controller.dump_character()
    saved_path = isolated_save_directories.chars / f"Eve.{controller.character.id}.character.yaml"
    before = saved_path.read_bytes()

    def broken_dump(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("data.persistence.yaml.safe_dump", broken_dump)
    controller.character.name = "Eve Renamed"
    with pytest.raises(RuntimeError):
        controller.dump_character()
    assert saved_path.read_bytes() == before
    assert [p.name for p in isolated_save_directories.chars.iterdir() if p.is_file()] == [saved_path.name]


def test_load_state_reads_legacy_python_tags(controller, isolated_save_directories):
    legacy = (
        "minus_hp: 4\n"
        "statuses:\n"
        "- !!python/object/apply:data.models.status.Status\n"
        "  - dazed\n"
    )
    (isolated_save_directories.states / f"{controller.character.id}.yaml").write_text(legacy, encoding="utf-8")
    controller.load_state()
    assert controller.state.minus_hp == 4
    assert [s.value for s in controller.state.statuses] == ["dazed"]


def test_load_character_works_on_a_copy(controller, isolated_save_directories):
    saved = Character(name="Frank", level=7)
    with pytest.raises(Exception):  # no state file yet
        controller.load_character(saved)
    controller.character.level = 8
    assert saved.level == 7


def test_unsaved_changes_tracking(controller, isolated_save_directories):
    controller.character.name = "Grace"
    controller.save()
    assert not controller.has_unsaved_changes()

    controller.character.might.current = 6  # derived by apply_status, not an edit
    assert not controller.has_unsaved_changes()

    controller.character.level = 9
    assert controller.has_unsaved_changes()
    controller.save()
    assert not controller.has_unsaved_changes()

    controller.state.minus_hp = 3
    assert controller.has_unsaved_changes()
