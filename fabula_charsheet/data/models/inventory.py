from __future__ import annotations
from annotated_types import Len
from pydantic import BaseModel, Discriminator, Field, Tag, model_validator
from typing import Annotated, Any

from .item import Item
from .weapon import Weapon
from .armor import Armor
from .shield import Shield
from .accessory import Accessory


# Fields only a weapon has. A shield dumped to YAML has none of them.
_WEAPON_ONLY_FIELDS = {"grip_type", "range", "weapon_category", "damage_type", "accuracy"}


def _off_hand_kind(value: Any) -> str:
    # Without this, pydantic reads a saved shield as a Weapon: every extra
    # Weapon field has a default, so the shield's data fits it too.
    if isinstance(value, dict):
        return "weapon" if _WEAPON_ONLY_FIELDS & value.keys() else "shield"
    return "shield" if isinstance(value, Shield) else "weapon"


OffHandItem = Annotated[
    Annotated[Weapon, Tag("weapon")] | Annotated[Shield, Tag("shield")],
    Discriminator(_off_hand_kind),
]


class Equipped(BaseModel):
    main_hand: Weapon | None = None
    off_hand: OffHandItem | None = None
    armor: Armor | None = None
    accessory: Accessory | None = None

class Backpack(BaseModel):
    armors: list[Armor] = list()
    weapons: list[Weapon] = list()
    shields: list[Shield] = list()
    accessories: list[Accessory] = list()
    other: list[Item] = list()

    def all_items(self):
        items = []
        items.extend(self.armors)
        items.extend(self.weapons)
        items.extend(self.shields)
        items.extend(self.accessories)
        items.extend(self.other)

        return items

    def add_item(self, item: Item):
        if isinstance(item, Weapon):
            self.weapons.append(item)
        elif isinstance(item, Armor):
            self.armors.append(item)
        elif isinstance(item, Shield):
            self.shields.append(item)
        elif isinstance(item, Accessory):
            self.accessories.append(item)
        else:
            self.other.append(item)

    def remove_item(self, item: Item):
        # By identity, not equality: with two identical daggers, remove this one.
        if isinstance(item, Weapon):
            items = self.weapons
        elif isinstance(item, Armor):
            items = self.armors
        elif isinstance(item, Shield):
            items = self.shields
        elif isinstance(item, Accessory):
            items = self.accessories
        else:
            items = self.other
        for i, candidate in enumerate(items):
            if candidate is item:
                del items[i]
                return
        raise ValueError(f"{item.name} is not in the backpack")

EQUIPPED_SLOTS = ("main_hand", "off_hand", "armor", "accessory")


class Inventory(BaseModel):
    zenit: int = 0
    equipped: Equipped = Field(default_factory=Equipped)
    backpack: Backpack = Field(default_factory=Backpack)

    @model_validator(mode="after")
    def _link_equipped_to_backpack(self):
        """Equipped items are the backpack's own objects, and code compares them
        by identity (so two identical daggers stay two different items). A saved
        file stores them twice, as equal copies; point each slot back at a
        not-yet-used equal backpack item. Items not in the backpack (e.g. the
        Twin Shields weapon) are left as they are."""
        used: set[int] = set()
        for slot in EQUIPPED_SLOTS:
            item = getattr(self.equipped, slot)
            if item is None:
                continue
            for candidate in self.backpack.all_items():
                if id(candidate) not in used and candidate == item:
                    setattr(self.equipped, slot, candidate)
                    used.add(id(candidate))
                    break
        return self
