from __future__ import annotations

from pydantic import BaseModel
from typing import TYPE_CHECKING

from .status import Status
from .damage import DamageType
from .species import Species

if TYPE_CHECKING:
    from data.models import LocNamespace


class Item(BaseModel):
    name: str = ""
    cost: int = 0
    quality: str = "no_quality"
    quality_detail: list[Status | DamageType | Species] = list()
    bonus_defense: int = 0
    bonus_magic_defense: int = 0
    bonus_initiative: int = 0

    def localized_name(self, loc: LocNamespace) -> str:
        key = f"item_{self.name}"
        try:
            return getattr(loc, key)
        except AttributeError:
            # custom item: keep the user's casing, only capitalize the first letter
            return self.name[:1].upper() + self.name[1:]

    def localized_quality(self, loc: LocNamespace) -> str:
        if self.quality == "no_quality":
            return getattr(loc, "item_no_quality", self.quality)
        elif self.quality == "improvised":
            return getattr(loc, "improvised_quality", self.quality)
        else:
            try:
                loc_quality =  getattr(loc, f"quality_{self.quality}_short")
            except AttributeError:
                return self.quality
            if self.quality_detail:
                try:
                    return loc_quality.format(*[q.localized_name(loc) for q in self.quality_detail])
                except (IndexError, KeyError, ValueError):
                    # quality_detail doesn't match the placeholders in the translation
                    pass
            return loc_quality
