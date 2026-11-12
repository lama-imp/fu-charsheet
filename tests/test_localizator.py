import re
import string
from pathlib import Path

import pytest
import yaml

from data.localizator import init_localizator, load_translations, Localizator
from data.models import LangEnum


def test_init_localizator_loads_translations(streamlit_stub, tmp_path):
    en_dir = tmp_path / 'en'
    ru_dir = tmp_path / 'ru'
    en_dir.mkdir()
    ru_dir.mkdir()
    (en_dir / 'base.yaml').write_text('{"error_name_empty": "Name should not be empty.", "bond_explanation": "About Bonds"}', encoding='utf-8')
    (ru_dir / 'base.yaml').write_text('{"error_name_empty": "Имя не должно быть пустым."}', encoding='utf-8')
    init_localizator(tmp_path)
    localizator = streamlit_stub.session_state['localizator']
    en = localizator.get(LangEnum.en)
    ru = localizator.get(LangEnum.ru)
    assert en.error_name_empty == "Name should not be empty."
    assert ru.error_name_empty == "Имя не должно быть пустым."
    assert ru.bond_explanation == en.bond_explanation


def test_init_localizator_duplicate_keys(tmp_path, streamlit_stub):
    en_dir = tmp_path / 'en'
    ru_dir = tmp_path / 'ru'
    en_dir.mkdir()
    ru_dir.mkdir()
    (en_dir / 'a.yaml').write_text('{"key1": "value1"}')
    (en_dir / 'b.yaml').write_text('{"key1": "value2"}')
    (ru_dir / 'a.yaml').write_text('{"key1": "value1"}')
    with pytest.raises(ValueError):
        init_localizator(tmp_path)


def test_blank_translation_falls_back_to_english(tmp_path):
    (tmp_path / 'en').mkdir()
    (tmp_path / 'ru').mkdir()
    (tmp_path / 'en' / 'base.yaml').write_text('{"a": "A", "b": "B"}', encoding='utf-8')
    (tmp_path / 'ru' / 'base.yaml').write_text('{"a": "", "b": null}', encoding='utf-8')
    translations = load_translations(tmp_path)
    assert translations[LangEnum.ru] == {"a": "A", "b": "B"}


def test_unknown_language_falls_back_to_english():
    localizator = Localizator({LangEnum.en: {"a": "A"}})
    assert localizator.get(LangEnum.ru).a == "A"


# --- Checks against the real locale files and source code ---

_SOURCE_DIR = Path(__file__).resolve().parents[1] / 'fabula_charsheet'
_LOCALS_DIR = _SOURCE_DIR / 'assets' / 'locals'
# Literal key accesses: `loc.key`, `self.loc.key`, `getattr(loc, "key")`
_LOC_ATTR = re.compile(r"\bloc\.([A-Za-z_]\w*)")
_LOC_GETATTR = re.compile(r"getattr\(\s*(?:self\.)?loc\s*,\s*[\"']([^\"']+)[\"']\s*\)")


def _english_keys() -> set[str]:
    return set(load_translations(_LOCALS_DIR)[LangEnum.en])


def test_every_literal_key_used_in_code_exists_in_english():
    english = _english_keys()
    missing = []
    for py_file in _SOURCE_DIR.rglob('*.py'):
        source = py_file.read_text(encoding='utf-8')
        keys = set(_LOC_ATTR.findall(source)) | set(_LOC_GETATTR.findall(source))
        keys -= {'root'}
        missing += [f"{py_file.relative_to(_SOURCE_DIR)}: {key}" for key in sorted(keys - english)]
    assert not missing, "Translation keys missing from English (no fallback possible):\n" + "\n".join(missing)


@pytest.mark.parametrize('lang', [lang for lang in LangEnum if lang != LangEnum.en])
def test_translation_keys_exist_in_english(lang):
    # A key only present in a translation is a typo or stale key: English users would never see it
    lang_keys = set()
    for yaml_file in (_LOCALS_DIR / lang).rglob('*.yaml'):
        lang_keys |= set(yaml.safe_load(yaml_file.read_text(encoding='utf-8')) or {})
    assert sorted(lang_keys - _english_keys()) == []


@pytest.mark.parametrize('lang', [lang for lang in LangEnum if lang != LangEnum.en])
def test_translation_placeholders_match_english(lang):
    translations = load_translations(_LOCALS_DIR)
    english, other = translations[LangEnum.en], translations[lang]

    def fields(text: str) -> set[str]:
        return {name for _, name, _, _ in string.Formatter().parse(text) if name is not None}

    mismatched = [key for key in english if fields(english[key]) != fields(other[key])]
    assert mismatched == []
