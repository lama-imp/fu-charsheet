from __future__ import annotations
from pydantic import BaseModel, Field, field_validator

from .therioform import Therioform
from .status import Status
from .attributes import AttributeName


class CharState(BaseModel):
    minus_hp: int = 0
    minus_mp: int = 0
    minus_ip: int = 0
    companion_minus_hp: int = 0
    fabula_points: int = Field(default=0, ge=0)
    statuses: list[Status] = list()
    improved_attributes: list[AttributeName] = list()
    active_therioforms: list[Therioform] = list()

    @field_validator("improved_attributes", mode="before")
    @classmethod
    def _drop_legacy_entries(cls, value):
        # Older versions declared this as list[Attribute] and saved every entry
        # as an empty mapping (`- {}`), so those entries carry no information.
        # Keep only real attribute names, once each.
        if not isinstance(value, list):
            return value
        names = []
        for entry in value:
            if isinstance(entry, str) and entry in AttributeName.__members__ and entry not in names:
                names.append(entry)
        return names
