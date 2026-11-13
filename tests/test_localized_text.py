from data.models import Item, LocNamespace
from data.models.character import CharacterTheme


EN = LocNamespace(root={"theme_hope": "Hope", "item_dagger": "Dagger"})
RU = LocNamespace(root={"theme_hope": "Надежда"})


def test_theme_from_stored_enum_value():
    assert CharacterTheme.from_stored("hope") is CharacterTheme.hope


def test_theme_from_stored_legacy_localized_text_any_language():
    # older saves stored the theme already localized, in whichever language was active
    assert CharacterTheme.from_stored("Надежда", [EN, RU]) is CharacterTheme.hope
    assert CharacterTheme.from_stored(" Hope ", [EN, RU]) is CharacterTheme.hope


def test_theme_from_stored_unknown_or_empty():
    assert CharacterTheme.from_stored("", [EN]) is None
    assert CharacterTheme.from_stored("Revenge of the nerds", [EN, RU]) is None


def test_custom_item_name_keeps_user_casing():
    assert Item(name="Sword of McGuffin").localized_name(EN) == "Sword of McGuffin"
    assert Item(name="sword of mcguffin").localized_name(EN) == "Sword of mcguffin"


def test_compendium_item_name_is_localized():
    assert Item(name="dagger").localized_name(EN) == "Dagger"


def test_item_default_quality_is_key():
    assert Item(name="x").quality == "no_quality"
