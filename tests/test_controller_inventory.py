import pytest

from data.models import (
    Armor,
    Character,
    CharClass,
    ClassName,
    GripType,
    HeroicSkill,
    HeroicSkillName,
    Quality,
    Shield,
    Skill,
    Weapon,
)


def dagger():
    return Weapon(name="dagger", grip_type=GripType.one_handed)


# --- identical items are still different items ---

def test_two_identical_daggers_can_be_dual_wielded(controller):
    first, second = dagger(), dagger()
    controller.add_item(first)
    controller.add_item(second)
    controller.equip_item(first)
    assert controller.is_equipped(first)
    assert not controller.is_equipped(second)  # equal, but not the one in hand
    controller.equip_item(second)
    equipped = controller.character.inventory.equipped
    assert equipped.main_hand is first
    assert equipped.off_hand is second


def test_remove_item_removes_and_unequips_that_exact_copy(controller):
    first, second = dagger(), dagger()
    controller.add_item(first)
    controller.add_item(second)
    controller.equip_item(first)
    controller.remove_item(second)
    assert controller.character.inventory.equipped.main_hand is first
    assert controller.character.inventory.backpack.weapons == [first]
    assert controller.character.inventory.backpack.weapons[0] is first


def test_equipped_items_are_linked_to_backpack_after_save_and_load(controller):
    first, second = dagger(), dagger()
    armor = Armor(name="leather")
    for item in (first, second, armor):
        controller.add_item(item)
    controller.equip_item(first)
    controller.equip_item(second)
    controller.equip_item(armor)

    reloaded = Character(**controller.character.model_dump(mode="json"))

    inventory = reloaded.inventory
    assert inventory.equipped.main_hand is inventory.backpack.weapons[0]
    assert inventory.equipped.off_hand is inventory.backpack.weapons[1]
    assert inventory.equipped.armor is inventory.backpack.armors[0]


def test_load_character_copy_keeps_equipped_items_linked(controller):
    item = dagger()
    controller.add_item(item)
    controller.equip_item(item)
    saved = controller.character
    controller.load_character(saved)
    inventory = controller.character.inventory
    assert inventory.equipped.main_hand is inventory.backpack.weapons[0]
    assert inventory.equipped.main_hand is not item  # it is a copy


# --- shields and two-handed weapons ---

def _with_dual_shieldbearer(controller):
    controller.character.classes = [
        CharClass(name=ClassName.guardian, skills=[Skill(name="dual_shieldbearer", current_level=1, max_level=1)])
    ]


def test_dual_shieldbearer_shield_clears_two_handed_main_hand(controller):
    _with_dual_shieldbearer(controller)
    equipped = controller.character.inventory.equipped
    equipped.main_hand = Weapon(name="greatsword", grip_type=GripType.two_handed)
    controller.equip_item(Shield(name="buckler"))
    assert equipped.main_hand is None
    assert equipped.off_hand.name == "buckler"


def test_dual_shieldbearer_with_monkey_grip_keeps_two_handed_main_hand(controller):
    _with_dual_shieldbearer(controller)
    controller.character.heroic_skills = [HeroicSkill(name=HeroicSkillName.monkey_grip)]
    equipped = controller.character.inventory.equipped
    equipped.main_hand = Weapon(name="greatsword", grip_type=GripType.two_handed)
    controller.equip_item(Shield(name="buckler"))
    assert equipped.main_hand.name == "greatsword"


def test_dual_shieldbearer_same_shield_twice_does_not_make_twin_shields(controller):
    _with_dual_shieldbearer(controller)
    shield = Shield(name="buckler")
    controller.equip_item(shield)
    controller.equip_item(shield)
    assert controller.character.inventory.equipped.main_hand is None


# --- quality upgrades ---

def test_upgrade_item_replacing_a_quality_removes_the_old_bonus(controller):
    controller.character.inventory.zenit = 2000
    armor = Armor(name="leather", bonus_defense=0, bonus_magic_defense=0)
    controller.upgrade_item(armor, Quality(name="bulwark", cost=800), [])
    assert (armor.bonus_defense, armor.bonus_magic_defense) == (1, 0)
    controller.upgrade_item(armor, Quality(name="amulet", cost=800), [])
    assert (armor.bonus_defense, armor.bonus_magic_defense) == (0, 1)
    assert armor.quality == "amulet"
    assert controller.character.inventory.zenit == 400


def test_upgrade_item_without_enough_zenit_changes_nothing(controller):
    controller.character.inventory.zenit = 500
    armor = Armor(name="leather")
    with pytest.raises(ValueError):
        controller.upgrade_item(armor, Quality(name="bulwark", cost=800), [])
    assert armor.quality == "no_quality"
    assert armor.bonus_defense == 0
    assert controller.character.inventory.zenit == 500


def test_upgrade_item_unequips_that_item(controller):
    controller.character.inventory.zenit = 1000
    first, second = dagger(), dagger()
    controller.add_item(first)
    controller.add_item(second)
    controller.equip_item(first)
    controller.equip_item(second)
    controller.upgrade_item(second, Quality(name="bulwark", cost=800), [])
    equipped = controller.character.inventory.equipped
    assert equipped.main_hand is first
    assert equipped.off_hand is None


# --- zenit ---

def test_spend_zenit_never_goes_negative(controller):
    controller.character.inventory.zenit = 100
    assert controller.can_afford(100)
    assert not controller.can_afford(101)
    with pytest.raises(ValueError):
        controller.spend_zenit(150)
    assert controller.character.inventory.zenit == 100
    controller.spend_zenit(100)
    assert controller.character.inventory.zenit == 0


def test_equipped_shield_is_still_a_shield_after_save_and_load(controller):
    shield = Shield(name="buckler", bonus_defense=2)
    controller.add_item(shield)
    controller.equip_item(shield)
    reloaded = Character(**controller.character.model_dump(mode="json"))
    off_hand = reloaded.inventory.equipped.off_hand
    assert isinstance(off_hand, Shield)
    assert off_hand is reloaded.inventory.backpack.shields[0]


def test_equipped_off_hand_weapon_is_still_a_weapon_after_save_and_load(controller):
    first, second = dagger(), dagger()
    controller.add_item(first)
    controller.add_item(second)
    controller.equip_item(first)
    controller.equip_item(second)
    reloaded = Character(**controller.character.model_dump(mode="json"))
    assert isinstance(reloaded.inventory.equipped.off_hand, Weapon)
