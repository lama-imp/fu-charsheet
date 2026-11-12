import pytest

from data.models import Armor, CharClass, ClassName, Shield, Skill, Spell, Weapon, WeaponRange


def _class(name, *levels, **kwargs):
    skills = [Skill(name=f"{name}_skill_{i}", current_level=lvl, max_level=10) for i, lvl in enumerate(levels)]
    return CharClass(name=name, skills=skills, **kwargs)


# --- remove_class ---

def test_remove_class_also_removes_its_spells(controller):
    controller.character.classes = [_class(ClassName.elementalist, 2), _class(ClassName.rogue, 3)]
    controller.character.spells = {
        ClassName.elementalist: [Spell(name="fireball", mp_cost=10)],
        ClassName.rogue: [],
    }
    controller.remove_class(ClassName.elementalist)
    assert [c.name for c in controller.character.classes] == [ClassName.rogue]
    assert ClassName.elementalist not in controller.character.spells


def test_remove_class_without_spells_is_fine(controller):
    controller.character.classes = [_class(ClassName.rogue, 3)]
    controller.remove_class(ClassName.rogue)
    assert controller.character.classes == []


# --- skill_points_left_with ---

def test_skill_points_left_for_a_new_class(controller):
    controller.character.level = 5
    controller.character.classes = [_class(ClassName.rogue, 2)]
    assert controller.skill_points_left_with(_class(ClassName.guardian, 3)) == 0
    assert controller.skill_points_left_with(_class(ClassName.guardian, 4)) == -1


def test_skill_points_left_counts_the_edited_class_not_the_old_one(controller):
    controller.character.level = 5
    controller.character.classes = [_class(ClassName.rogue, 2), _class(ClassName.guardian, 3)]
    # Before the edit everything is spent (can_add_skill_number == 0) ...
    assert controller.can_add_skill_number() == 0
    # ... raising the guardian from 3 to 5 levels would overspend by 2.
    assert controller.skill_points_left_with(_class(ClassName.guardian, 5)) == -2
    # Lowering it frees points.
    assert controller.skill_points_left_with(_class(ClassName.guardian, 1)) == 2


# --- equip_item martial restrictions ---

@pytest.mark.parametrize("item", [
    Weapon(name="bow", martial=True, range=WeaponRange.ranged),
    Armor(name="plate", martial=True),
    Shield(name="tower_shield", martial=True),
])
def test_equip_item_refuses_martial_item_without_class_support(controller, item):
    controller.character.classes = []
    with pytest.raises(Exception):
        controller.equip_item(item)
    assert controller.equipped_items() == []


def test_equip_item_allows_martial_item_with_class_support(controller):
    controller.character.classes = [CharClass(name=ClassName.guardian, martial_armor=True)]
    armor = Armor(name="plate", martial=True)
    controller.equip_item(armor)
    assert controller.character.inventory.equipped.armor == armor


def test_can_equip_martial_accepts_items_without_martial_field(controller):
    from data.models import Accessory
    assert controller.can_equip_martial(Accessory(name="ring")) is True


def test_remove_class_unequips_martial_items_it_allowed(controller):
    guardian = CharClass(name=ClassName.guardian, martial_armor=True, martial_shields=True)
    controller.character.classes = [guardian, _class(ClassName.rogue, 3)]
    armor = Armor(name="plate", martial=True)
    shield = Shield(name="tower_shield", martial=True)
    dagger = Weapon(name="dagger", martial=False)
    for item in (armor, shield, dagger):
        controller.add_item(item)
        controller.equip_item(item)

    controller.remove_class(ClassName.guardian)

    equipped = controller.character.inventory.equipped
    assert equipped.armor is None
    assert shield not in controller.equipped_items()
    assert equipped.main_hand == dagger  # non-martial gear stays equipped
    assert armor in controller.character.inventory.backpack.armors  # still owned


def test_remove_class_keeps_martial_items_another_class_allows(controller):
    controller.character.classes = [
        CharClass(name=ClassName.guardian, martial_armor=True),
        CharClass(name=ClassName.dark_blade, martial_armor=True),
    ]
    armor = Armor(name="plate", martial=True)
    controller.equip_item(armor)
    controller.remove_class(ClassName.guardian)
    assert controller.character.inventory.equipped.armor == armor
