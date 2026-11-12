from __future__ import annotations
import math
from pathlib import Path
from typing import TYPE_CHECKING

from config import (
    SAVED_CHARS_DIRECTORY,
    SAVED_CHARS_IMG_DIRECTORY,
    SAVED_STATES_DIRECTORY,
    MIN_ATTRIBUTE_VALUE,
    MAX_ATTRIBUTE_VALUE,
)
from data import compendium as c
from data.persistence import atomic_write, dump_yaml, load_yaml, safe_filename
from data.models import (
    Character,
    CharClass,
    Ritual,
    Skill,
    HeroicSkill,
    HeroicSkillName,
    ClassName,
    Spell,
    SpellTarget,
    DamageType,
    Accessory,
    Shield,
    Weapon,
    Armor,
    Item,
    CharState,
    Status,
    AttributeName,
    GripType,
    Quality,
    Therioform,
    Companion,
    CompanionSkillName,
    SPECIES_STARTING_SKILLS,
    MAX_LEVEL,
)

if TYPE_CHECKING:
    from streamlit.runtime.uploaded_file_manager import UploadedFile
    from data.models import LocNamespace

from config import ATTRIBUTE_SUM_AT_LEVEL_20, ATTRIBUTE_SUM_AT_LEVEL_40


class StateLoadError(Exception):
    """The saved battle state exists but could not be read."""

    def __init__(self, path: Path, cause: Exception):
        super().__init__(f"{path.name}: {cause}")
        self.path = path
        self.cause = cause


class CharacterController:
    def __init__(self, loc: LocNamespace):
        self.character = Character()
        self.loc = loc
        self.state = CharState()
        # What was last loaded from / written to disk, to detect unsaved edits.
        self._saved_snapshot: dict | None = None

    def get_character(self):
        return self.character

    def has_enough_skills(self):
        if not self.character.classes:
            return False
        if self.character.get_n_skill() != self.character.level:
            return False
        return True

    def add_class(self, new_class: CharClass):
        self.character.classes.append(new_class)

    def update_class(self, updated_class: CharClass):
        for i, existing in enumerate(self.character.classes):
            if existing.name == updated_class.name:
                self.character.classes[i] = updated_class
                return
        msg = self.loc.error_class_not_found.format(class_name=updated_class.name)
        raise ValueError(msg)

    def remove_class(self, class_name: ClassName):
        """Remove a class together with the spells learned through it."""
        self.character.classes = [c for c in self.character.classes if c.name != class_name]
        self.character.spells.pop(class_name, None)
        self.unequip_disallowed_items()

    def unequip_disallowed_items(self):
        """Unequip martial items none of the character's classes allow any more.
        They stay in the backpack."""
        equipped = self.character.inventory.equipped
        for category in ("main_hand", "off_hand", "armor"):
            item = getattr(equipped, category)
            if item is not None and not self.can_equip_martial(item):
                setattr(equipped, category, None)

    def can_add_skill_number(self):
        return self.character.level - self.character.get_n_skill()

    def skill_points_left_with(self, char_class: CharClass) -> int:
        """Skill points left if `char_class` (being added, or an edited copy of a
        class the character has) were applied. Negative means too many."""
        existing = self.character.get_class(char_class.name)
        used = self.character.get_n_skill() - (existing.class_level() if existing else 0)
        return self.character.level - used - char_class.class_level()

    def is_class_added(self, new_class: CharClass | str | None):
        if new_class is None:
            return False
        elif isinstance(new_class, CharClass):
            class_name = new_class.name
        elif isinstance(new_class, str):
            class_name = new_class.lower()
        else:
            msg = self.loc.error_unexpected_class_type.format(class_type=type(new_class))
            raise ValueError(msg)

        return any(c.name == class_name for c in self.character.classes)

    def has_skill(self, skill_name: str) -> bool:
        for char_class in self.character.classes:
            if char_class.get_skill(skill_name) and char_class.get_skill(skill_name).current_level > 0:
                return True
        return False

    def get_skills(self, class_name: ClassName) -> list[Skill]:
        if class_name in [c.name for c in self.character.classes]:
            idx = [c.name for c in self.character.classes].index(class_name)
            return self.character.classes[idx].skills
        return []

    def get_skill_level(self, char_class_name: ClassName, skill_name: str) -> int | None:
        for char_class in self.character.classes:
            if char_class.name == char_class_name:
                return char_class.get_skill_level(skill_name)

    def add_spell(self, spell: Spell, class_name: ClassName):
        if spell not in self.character.spells.get(class_name, []):
            self.character.spells[class_name] = self.character.spells.get(class_name, [])
            self.character.spells[class_name].append(spell)

    def remove_spell(self, spell: Spell, class_name: ClassName):
        if spell in self.character.spells.get(class_name, []):
            self.character.spells[class_name].remove(spell)

    def max_hp(self) -> int:
        base_hp = (
                self.character.level
                + self.character.might.base * 5
                + sum([c.bonus_value for c in self.character.classes if c.class_bonus == "hp"])
        )
        bonus = 0
        if self.character.has_heroic_skill(HeroicSkillName.extra_hp):
            if self.character.level < 40:
                bonus += 10
            else:
                bonus += 20
        bonus += 3 * (self.get_skill_level(ClassName.guardian, "fortress") or 0)

        return base_hp + bonus

    def max_mp(self) -> int:
        base_mp = (
                self.character.level
                + self.character.willpower.base * 5
                + sum([c.bonus_value for c in self.character.classes if c.class_bonus == "mp"])
        )
        bonus = 0
        if self.character.has_heroic_skill(HeroicSkillName.extra_mp):
            if self.character.level < 40:
                bonus += 10
            else:
                bonus += 20
        bonus += 3 * (self.get_skill_level(ClassName.loremaster, "focused") or 0)

        return base_mp + bonus

    def max_ip(self) -> int:
        base_ip =  (
                6
                + sum([c.bonus_value for c in self.character.classes if c.class_bonus == "ip"])
        )
        bonus = 0
        if self.character.has_heroic_skill(HeroicSkillName.extra_ip):
            bonus += 4

        return base_ip + bonus

    def current_hp(self) -> int:
        return self.max_hp() - self.state.minus_hp

    def current_mp(self) -> int:
        return self.max_mp() - self.state.minus_mp

    def current_ip(self) -> int:
        return self.max_ip() - self.state.minus_ip

    def defense(self):
        item_bonus = 0
        for item in self.equipped_items():
            item_bonus += item.bonus_defense

        other_bonuses = 0
        armor = self.character.inventory.equipped.armor
        # Rogue's Dodge only works with no shields and no martial armor equipped.
        equipped = self.character.inventory.equipped
        has_shield = isinstance(equipped.main_hand, Shield) or isinstance(equipped.off_hand, Shield)
        has_martial_armor = armor is not None and armor.martial
        if not has_shield and not has_martial_armor:
            other_bonuses += self.get_skill_level(ClassName.rogue, "dodge") or 0

        if armor:
            if isinstance(armor.defense, int):
                armor_defense = armor.defense
            else:
                armor_defense = self.character.dexterity.current
            defense = (armor_defense
                        + item_bonus
                        + other_bonuses)
        else:
            defense = (self.character.dexterity.current
                        + item_bonus
                        + other_bonuses)
        if "placophora" in [t.name for t in self.state.active_therioforms]:
            t_defense = 13 + math.floor(self.get_skill_level(ClassName.mutant, "theriomorphosis") / 2)
            if t_defense > defense:
                defense = t_defense

        return defense

    def magic_defense(self):
        bonus = 0
        for item in self.equipped_items():
            bonus += item.bonus_magic_defense

        return self.character.insight.current + bonus

    def initiative(self) -> str:
        initiative = f"{self.loc.dice_prefix}{self.character.insight.current} + {self.loc.dice_prefix}{self.character.dexterity.current}"
        bonus = 0
        for item in self.equipped_items():
            bonus += item.bonus_initiative

        if bonus and bonus < 0:
            return f"{initiative} {bonus}"
        elif bonus and bonus > 0:
            return f"{initiative} +{bonus}"
        return initiative

    def can_equip_martial(self, item: Item) -> bool:
        # Accessories and plain items have no `martial` field and are never martial.
        if not getattr(item, "martial", False):
            return True
        if isinstance(item, Weapon):
            return any(c.can_equip_weapon(item.range) for c in self.character.classes)
        if isinstance(item, Armor):
            return any(c.martial_armor for c in self.character.classes)
        if isinstance(item, Shield):
            return any(c.martial_shields for c in self.character.classes)
        return False

    def equip_item(self, item: Item):
        if not self.can_equip_martial(item):
            raise Exception(self.loc.error_equipping_martial)
        equipped = self.character.inventory.equipped

        if isinstance(item, Armor):
            equipped.armor = item

        elif isinstance(item, Accessory):
            equipped.accessory = item

        elif isinstance(item, Weapon):
            is_two_handed = item.grip_type == "two_handed"
            can_dual_two_handed = self.character.has_heroic_skill(HeroicSkillName.monkey_grip)

            if is_two_handed and not can_dual_two_handed:
                # Two-handed weapon without special skill → clears both hands
                equipped.main_hand = item
                equipped.off_hand = None
            else:
                # Treat weapon as one-handed (normal or skill-enabled two-handed)
                if equipped.main_hand is None:
                    equipped.main_hand = item
                elif equipped.off_hand is None:
                    # Dual wield with one-handers or dual two-handers (if skilled)
                    if (equipped.main_hand.grip_type == "one_handed" or
                            (equipped.main_hand.grip_type == "two_handed" and can_dual_two_handed)):
                        equipped.off_hand = item
                    else:
                        equipped.main_hand = item  # incompatible → replace
                else:
                    # both occupied → replace main hand by default
                    equipped.main_hand = item
        elif isinstance(item, Shield):
            # --- Dual Shieldbearer: a second shield becomes the Twin Shields weapon ---
            if (self.has_skill("dual_shieldbearer")
                    and isinstance(equipped.off_hand, Shield)
                    and equipped.off_hand is not item):
                equipped.main_hand = Weapon(
                    name="twin_shields",
                    cost=item.cost,
                    accuracy=[AttributeName.might, AttributeName.might],
                    bonus_damage=5,
                    bonus_defense=item.bonus_defense,
                    bonus_magic_defense=item.bonus_magic_defense,
                )
            else:
                equipped.off_hand = item
                # A shield takes a hand: without Monkey Grip a two-handed
                # weapon can't stay in the main hand.
                if (not self.character.has_heroic_skill(HeroicSkillName.monkey_grip)
                        and isinstance(equipped.main_hand, Weapon)
                        and equipped.main_hand.grip_type == "two_handed"):
                    equipped.main_hand = None

        else:
            raise Exception(self.loc.error_equipping_item)

    def unequip_item(self, category: str):
        equipped = self.character.inventory.equipped
        if hasattr(equipped, category):
            setattr(equipped, category, None)

    def equipped_items(self) -> list[Item]:
        equipped = self.character.inventory.equipped
        return [
            item
            for item in (equipped.main_hand, equipped.off_hand, equipped.armor, equipped.accessory)
            if item is not None
        ]

    def add_item(self, item: Item):
        self.character.inventory.backpack.add_item(item)

    def is_equipped(self, item: Item) -> bool:
        # Identity, not equality: of two identical daggers only the one in hand counts.
        return any(equipped is item for equipped in self.equipped_items())

    def remove_item(self, item: Item):
        equipped = self.character.inventory.equipped
        for category in ("main_hand", "off_hand", "armor", "accessory"):
            if getattr(equipped, category) is item:
                setattr(equipped, category, None)
        self.character.inventory.backpack.remove_item(item)

    def can_afford(self, cost: int) -> bool:
        return self.character.inventory.zenit >= cost

    def spend_zenit(self, amount: int):
        if amount < 0:
            raise ValueError(amount)
        if not self.can_afford(amount):
            raise ValueError(self.loc.error_not_enough_zenit.format(cost=amount, zenit=self.character.inventory.zenit))
        self.character.inventory.zenit -= amount

    def load_character(self, character: Character):
        """Start working on a copy of a saved character, so unsaved edits never
        leak into the saved-characters list. Raises if its state can't be loaded
        (the character is still loaded, with a default state)."""
        self.character = character.model_copy(deep=True)
        try:
            self.load_state()
        finally:
            self.mark_saved()

    def _snapshot(self) -> dict:
        # Attribute `current` values are derived from base + statuses by
        # apply_status(), so they are not user edits.
        derived = {"current"}
        character = self.character.model_dump(
            mode="json",
            exclude={"dexterity": derived, "might": derived, "insight": derived, "willpower": derived},
        )
        return {"character": character, "state": self.state.model_dump(mode="json")}

    def mark_saved(self):
        self._saved_snapshot = self._snapshot()

    def has_unsaved_changes(self) -> bool:
        return self._saved_snapshot is None or self._saved_snapshot != self._snapshot()

    def dump_character(self):
        char_id = self.character.id
        new_path = Path(
            SAVED_CHARS_DIRECTORY,
            f"{safe_filename(self.character.name)}.{char_id}.character.yaml",
        )
        dump_yaml(self.character.model_dump(mode="json"), new_path)
        # Only remove older files (e.g. from before a rename) once the new one is safely written.
        for old_file in SAVED_CHARS_DIRECTORY.glob(f"*.{char_id}.character.yaml"):
            if old_file != new_path:
                old_file.unlink(missing_ok=True)

    def dump_avatar(self, image: UploadedFile | None ):
        if image is not None:
            char_id = self.character.id
            image_file_path = Path(
                    SAVED_CHARS_IMG_DIRECTORY,
                    f"{safe_filename(self.character.name)}.{char_id}{Path(image.name).suffix.lower()}"
            )
            atomic_write(image_file_path, bytes(image.getbuffer()))
            for old_file in SAVED_CHARS_IMG_DIRECTORY.glob(f"*{char_id}.*"):
                if old_file != image_file_path:
                    old_file.unlink(missing_ok=True)

    def apply_status(self):
        dex_modifier = 0
        mig_modifier = 0
        ins_modifier = 0
        wlp_modifier = 0

        if Status.dazed in self.state.statuses:
            ins_modifier -= 2
        if Status.enraged in self.state.statuses:
            ins_modifier -= 2
            dex_modifier -= 2
        if Status.poisoned in self.state.statuses:
            mig_modifier -= 2
            wlp_modifier -= 2
        if Status.shaken in self.state.statuses:
            wlp_modifier -= 2
        if Status.slow in self.state.statuses:
            dex_modifier -= 2
        if Status.weak in self.state.statuses:
            mig_modifier -= 2

        for attribute in self.state.improved_attributes:
            match attribute:
                case AttributeName.dexterity:
                    dex_modifier += 2
                case AttributeName.might:
                    mig_modifier += 2
                case AttributeName.insight:
                    ins_modifier += 2
                case AttributeName.willpower:
                    wlp_modifier += 2

        for t in self.state.active_therioforms:
            match t.name:
                case "arpaktida":
                    ins_modifier += 2
                case "dynamotheria":
                    mig_modifier += 2
                case "tachytheria":
                    dex_modifier += 2

        self.character.insight.current = min(MAX_ATTRIBUTE_VALUE, max(MIN_ATTRIBUTE_VALUE, self.character.insight.base + ins_modifier))
        self.character.dexterity.current = min(MAX_ATTRIBUTE_VALUE, max(MIN_ATTRIBUTE_VALUE, self.character.dexterity.base + dex_modifier))
        self.character.willpower.current = min(MAX_ATTRIBUTE_VALUE, max(MIN_ATTRIBUTE_VALUE, self.character.willpower.base + wlp_modifier))
        self.character.might.current = min(MAX_ATTRIBUTE_VALUE, max(MIN_ATTRIBUTE_VALUE, self.character.might.base + mig_modifier))

    def crisis_value(self) -> int:
        return math.floor(self.max_hp() / 2)

    def can_add_heroic_skill(self) -> bool:
        mastered_classes = [char_class for char_class in self.character.classes if char_class.class_level() == 10]
        if len(mastered_classes) > len(self.character.heroic_skills):
            return True
        return False

    def is_heroic_skill_available(self, skill: HeroicSkill) -> bool:
        if skill in self.character.heroic_skills:
            return skill.can_add_several_times
        if skill.name == HeroicSkillName.heroic_companion and self.character.special.companion is None:
            return False
        if not skill.required_class:
            return True
        mastered_class_names = {char_class.name for char_class in self.character.classes if char_class.class_level() == 10}
        if set(skill.required_class).intersection(mastered_class_names):
            if skill.required_skill:
                return any(
                    (char_class.get_skill(skill.required_skill.name) or Skill()).current_level > 0
                    for char_class in self.character.classes
                )
            return True
        return False

    def can_add_class(self) -> bool:
        non_mastered_classes = [char_class for char_class in self.character.classes if char_class.class_level() < 10]
        return len(non_mastered_classes) < 3

    def can_increase_attribute(self) -> bool:
        sum_of_attributes = sum(
            [
                self.character.dexterity.base,
                self.character.might.base,
                self.character.insight.base,
                self.character.willpower.base,
            ]
        )
        # The increase is earned on reaching level 20 / 40 and stays available
        # until it is taken, so a skipped one is not lost on the next level-up.
        if self.character.level >= 40:
            return sum_of_attributes < ATTRIBUTE_SUM_AT_LEVEL_40
        if self.character.level >= 20:
            return sum_of_attributes < ATTRIBUTE_SUM_AT_LEVEL_20
        return False

    def add_status(self, status: Status):
        if status not in self.state.statuses:
            self.state.statuses.append(status)

    def remove_status(self, status: Status):
        if status in self.state.statuses:
            self.state.statuses.remove(status)

    def use_health_potion(self):
        self.state.minus_hp = max(0, self.state.minus_hp - 50)
        ip_cost = 2 if self.character.has_heroic_skill(heroic_skill_name=HeroicSkillName.deep_pockets) else 3
        self.state.minus_ip = min(self.max_ip(), self.state.minus_ip + ip_cost)

    def use_mana_potion(self):
        self.state.minus_mp = max(0, self.state.minus_mp - 50)
        ip_cost = 2 if self.character.has_heroic_skill(heroic_skill_name=HeroicSkillName.deep_pockets) else 3
        self.state.minus_ip = min(self.max_ip(), self.state.minus_ip + ip_cost)

    def use_magic_tent(self):
        self.state.minus_mp = 0
        self.state.minus_hp = 0
        ip_cost = 3 if self.character.has_heroic_skill(heroic_skill_name=HeroicSkillName.deep_pockets) else 4
        self.state.minus_ip = min(self.max_ip(), self.state.minus_ip + ip_cost)

    def can_use_potion(self) -> bool:
        ip_cost = (
            2
            if self.character.has_heroic_skill(
                heroic_skill_name=HeroicSkillName.deep_pockets
            )
            else 3
        )
        return self.current_ip() >= ip_cost

    def can_use_magic_tent(self) -> bool:
        ip_cost = (
            3
            if self.character.has_heroic_skill(
                heroic_skill_name=HeroicSkillName.deep_pockets
            )
            else 4
        )
        return self.current_ip() >= ip_cost

    def dump_state(self):
        dump_yaml(self.state.model_dump(mode="json"), Path(SAVED_STATES_DIRECTORY, f"{self.character.id}.yaml"))

    def save(self):
        """Save both the character and its battle state."""
        self.dump_character()
        self.dump_state()
        self.mark_saved()

    def load_state(self):
        """Load the saved battle state. A character that has never been saved
        with a state simply starts with a fresh one; a state file that exists
        but can't be read raises StateLoadError (and also starts fresh)."""
        state_path = Path(SAVED_STATES_DIRECTORY, f"{self.character.id}.yaml")
        self.state = CharState()
        if not state_path.exists():
            return
        try:
            self.state = CharState(**dict(load_yaml(state_path)))
        except Exception as e:
            raise StateLoadError(state_path, e) from e

    def can_level_up(self) -> bool:
        return self.character.level < MAX_LEVEL

    def apply_levelup(self, skill: Skill, class_name: ClassName, new_class: CharClass | None, spells: list[Spell]):
        """Gain one level: one level in `skill`, which belongs either to a class the
        character already has or to `new_class`, and the spells it grants (added to
        the spells already known, never replacing them).

        Everything is checked before anything changes, so a refused level-up
        leaves the character untouched."""
        if not self.can_level_up():
            raise ValueError(self.loc.error_invalid_level.format(level=self.character.level + 1))

        if self.is_class_added(class_name):
            target_class = self.character.get_class(class_name)
        elif new_class is not None and new_class.name == class_name:
            target_class = new_class
        else:
            raise ValueError(self.loc.error_levelup_skill_unavailable.format(skill=skill.name))

        target_skill = target_class.get_skill(skill.name)
        if target_skill is None or target_skill.current_level >= target_skill.max_level:
            raise ValueError(self.loc.error_levelup_skill_unavailable.format(skill=skill.name))

        if target_class is new_class:
            self.add_class(new_class)
        target_class.levelup_skill(skill.name)
        self.character.level += 1
        if skill.can_add_spell:
            for spell in spells:
                self.add_spell(spell, class_name)

    def add_heroic_skill(self, skill: HeroicSkill):
        self.character.heroic_skills.append(skill)
        self.apply_heroic_skill_effect(skill)

    def apply_heroic_skill_effect(self, skill: HeroicSkill):
        match skill.name:
            case HeroicSkillName.comet:
                self.add_spell(Spell(
                    name="comet",
                    mp_cost=50,
                    target=SpellTarget.special,
                    damage_type=DamageType.no_type,
                    char_class=ClassName.entropist,
                ), ClassName.entropist)
            case HeroicSkillName.hope:
                self.add_spell(Spell(
                    name="hope",
                    mp_cost=40,
                    target=SpellTarget.special,
                    char_class=ClassName.spiritist,
                ), ClassName.spiritist)
            case HeroicSkillName.volcano:
                self.add_spell(Spell(
                    name="volcano",
                    mp_cost=40,
                    target=SpellTarget.special,
                    damage_type=DamageType.fire,
                    char_class=ClassName.elementalist,
                ), ClassName.elementalist)

    # Stat bonuses some qualities add to the item they are put on.
    QUALITY_EFFECTS: dict[str, dict[str, int]] = {
        "amulet": {"bonus_magic_defense": 1},
        "bulwark": {"bonus_defense": 1},
        "omnishield": {"bonus_defense": 1, "bonus_magic_defense": 1},
        "initiative_up": {"bonus_initiative": 4},
    }

    def _change_quality_effects(self, item: Item, quality_name: str, sign: int):
        for field_name, bonus in self.QUALITY_EFFECTS.get(quality_name, {}).items():
            setattr(item, field_name, getattr(item, field_name) + sign * bonus)

    def apply_quality_effects(self, item: Item, quality: Quality):
        self._change_quality_effects(item, quality.name, +1)

    def upgrade_item(self, item: Item, quality: Quality, detail: list):
        """Give `item` a new quality, paying its cost. The old quality's
        bonuses are taken away first, so replacing a quality never stacks."""
        self.spend_zenit(quality.cost)
        for category in ("main_hand", "off_hand", "armor", "accessory"):
            if getattr(self.character.inventory.equipped, category) is item:
                self.unequip_item(category)
        self._change_quality_effects(item, item.quality, -1)
        item.quality = quality.name
        item.quality_detail = detail
        self.apply_quality_effects(item, quality)

    def chimerist_max_spells(self) -> int:
        max_n = (self.get_skill_level(ClassName.chimerist, "spell_mimic") or 0) + 2
        if self.character.has_heroic_skill(HeroicSkillName.chimeric_mastery):
            max_n += 2
        return max_n

    def can_add_spell(self, class_name: ClassName) -> bool:
        char_class = self.character.get_class(class_name)
        if char_class is None:
            return False
        casting_skill = char_class.get_spell_skill()
        if not casting_skill:
            return False
        return casting_skill.current_level > len(self.character.get_spells_by_class(class_name))

    INVENTION_TIERS = ("basic", "advanced", "superior")

    def can_add_invention(self) -> bool:
        """Each level of Gadgets grants one gadget benefit (a basic, advanced or superior tier)."""
        return len(self.character.special.inventions) < (
            self.get_skill_level(ClassName.tinkerer, "gadgets") or 0
        )

    def is_invention_available(self, invention) -> bool:
        """A tier can be taken only after the previous tier of the same gadget type."""
        owned = {i.name for i in self.character.special.inventions}
        if invention.name in owned:
            return False
        gadget_type, _, tier = invention.name.rpartition("_")
        if tier not in self.INVENTION_TIERS:
            return True
        tier_idx = self.INVENTION_TIERS.index(tier)
        return tier_idx == 0 or f"{gadget_type}_{self.INVENTION_TIERS[tier_idx - 1]}" in owned

    def can_add_therioform(self) -> bool:
        return len(self.character.special.therioforms) < (
            self.get_skill_level(ClassName.mutant, "theriomorphosis") or 0
        )

    def can_add_dance(self) -> bool:
        return len(self.character.special.dances) < (
            self.get_skill_level(ClassName.dancer, "dance") or 0
        )

    def available_therioforms_for_skill(self, skill_name: str) -> list[Therioform]:
        if skill_name == "theriomorphosis":
            return list(self.character.special.therioforms)
        if skill_name == "genoclepsis":
            return list(c.COMPENDIUM.therioforms)
        return []

    def max_manifest_therioforms(self, skill_name: str) -> int:
        if skill_name == "theriomorphosis":
            return 2
        if skill_name == "genoclepsis":
            return self.get_skill_level(ClassName.mutant, "genoclepsis") or 0
        return 0

    def can_manifest_therioform(self) -> bool:
        return self.current_hp() >= 3

    def apply_manifest_therioform(self, therioforms: list[Therioform]):
        self.state.minus_hp += math.floor(self.current_hp() / 3)
        self.state.active_therioforms = therioforms

    def companion_skill_level(self) -> int:
        return self.get_skill_level(ClassName.wayfarer, "faithful_companion") or 0

    def can_add_companion(self) -> bool:
        return self.has_skill("faithful_companion") and self.character.special.companion is None

    def companion_max_skills(self) -> int:
        companion = self.character.special.companion
        if companion is None:
            return 0
        max_skills = SPECIES_STARTING_SKILLS[companion.species]
        if self.character.has_heroic_skill(HeroicSkillName.heroic_companion):
            max_skills += 1
            if self.character.level >= 40:
                max_skills += 1
        return max_skills

    def apply_heroic_companion_attribute(self, attribute: AttributeName):
        companion = self.character.special.companion
        current = getattr(companion, attribute.value)
        setattr(companion, attribute.value, min(MAX_ATTRIBUTE_VALUE, current + 2))

    def companion_all_resistances(self) -> list[DamageType]:
        companion = self.character.special.companion
        resistances = list(companion.innate_resistances())
        for skill in companion.skills:
            if skill.name == CompanionSkillName.damage_resistance:
                resistances.extend(skill.damage_types)
        return resistances

    def companion_all_immunities(self) -> list[DamageType]:
        companion = self.character.special.companion
        immunities = list(companion.innate_immunities())
        for skill in companion.skills:
            if skill.name == CompanionSkillName.damage_immunity:
                immunities.extend(skill.damage_types)
        return immunities

    def companion_all_absorptions(self) -> list[DamageType]:
        companion = self.character.special.companion
        absorptions = []
        for skill in companion.skills:
            if skill.name == CompanionSkillName.damage_absorption:
                absorptions.extend(skill.damage_types)
        return absorptions

    def companion_all_vulnerabilities(self) -> list[DamageType]:
        return list(self.character.special.companion.innate_vulnerabilities())

    def companion_all_status_immunities(self) -> list[Status]:
        companion = self.character.special.companion
        immunities = list(companion.innate_status_immunities())
        for skill in companion.skills:
            if skill.name == CompanionSkillName.status_effect_immunity:
                immunities.extend(skill.statuses)
        return immunities

    def companion_max_hp(self) -> int:
        companion = self.character.special.companion
        improved_hp_count = sum(
            1 for skill in companion.skills if skill.name == CompanionSkillName.improved_hit_points
        )
        heroic_bonus = 10 if self.character.has_heroic_skill(HeroicSkillName.heroic_companion) else 0
        return (
            self.companion_skill_level() * companion.might
            + math.floor(self.character.level / 2)
            + 10 * improved_hp_count
            + heroic_bonus
        )

    def companion_crisis_value(self) -> int:
        return math.floor(self.companion_max_hp() / 2)

    def companion_current_hp(self) -> int:
        return max(0, self.companion_max_hp() - self.state.companion_minus_hp)

    def companion_defense(self) -> int:
        companion = self.character.special.companion
        bonus = 0
        for skill in companion.skills:
            if skill.name == CompanionSkillName.improved_defenses:
                bonus += 2 if skill.defense_option == "defense" else 1
        return companion.dexterity + bonus

    def companion_magic_defense(self) -> int:
        companion = self.character.special.companion
        bonus = 0
        for skill in companion.skills:
            if skill.name == CompanionSkillName.improved_defenses:
                bonus += 1 if skill.defense_option == "defense" else 2
        return companion.insight + bonus

    def companion_check_bonus(self) -> int:
        return self.companion_skill_level()

    def companion_attack_damage_bonus(self, attack_index: int) -> int:
        companion = self.character.special.companion
        return 5 * sum(
            1 for skill in companion.skills
            if skill.name == CompanionSkillName.improved_damage and skill.attack_index == attack_index
        )

    def set_companion(self, companion: Companion):
        self.character.special.companion = companion
        self.state.companion_minus_hp = 0

    def remove_companion(self):
        self.character.special.companion = None
        self.state.companion_minus_hp = 0

    def companion_flee(self):
        self.state.companion_minus_hp = self.companion_max_hp() - self.companion_crisis_value()


class ClassController:
    def __init__(self):
        self.char_class = CharClass()

    def add_ritual(self, ritual: Ritual):
        self.char_class.rituals.append(ritual)

    def add_skill(self, skill: Skill):
        self.char_class.skills.append(skill)
