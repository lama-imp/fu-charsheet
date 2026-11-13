import html
import uuid
from pathlib import Path
from copy import deepcopy
from itertools import chain

import streamlit as st

import config
from data.models import (
    Skill,
    Weapon,
    Armor,
    CharClass,
    Character,
    Shield,
    Item,
    Inventory,
    LocNamespace,
    Bond,
    Emotion,
    Quality,
    Status,
    DamageType,
    Species,
    CharacterTheme,
)
from pages.controller import ClassController, CharacterController
from data import compendium as c


def get_avatar_path(char_id: uuid.UUID) -> Path | None:
    for ext in ("jpg", "jpeg", "png", "gif"):
        matches = list(config.SAVED_CHARS_IMG_DIRECTORY.glob(f"*{char_id}.{ext}"))
        if matches:
            return matches[0]

    return None


def if_show_spells(casting_skill: Skill):
    if casting_skill and casting_skill.current_level > 0:
        return True
    return False


def list_skills(class_controller: ClassController, can_add_skill_number: int, loc: LocNamespace):
    with st.container(border=True):
        st.subheader(loc.msg_skills_points_remaining.format(count=can_add_skill_number))
        st.write(loc.msg_skills_selected)
        for skill in class_controller.char_class.skills:
            if skill.current_level > 0:
                show_skill(skill, loc)


def show_skill(skill: Skill, loc: LocNamespace):
    st.markdown(loc.msg_skill_with_level.format(name=f"**{skill.localized_name(loc)}**", level=skill.current_level))


def show_martial(input_: CharClass | Character, loc: LocNamespace):
    martial_keys = [
        "melee",
        "ranged",
        "armor",
        "shields",
    ]

    martial = {key: getattr(loc, key) for key in martial_keys}

    if isinstance(input_, CharClass):
        can_equip = input_.can_equip_list()
    else:
        can_equip = set(chain.from_iterable([x.can_equip_list() for x in input_.classes]))

    can_equip = [m[8:] for m in can_equip]

    if can_equip:
        can_equip_items = join_with_and([martial[m] for m in can_equip if m in martial], loc)
        st.write(loc.msg_can_equip_martial.format(items=can_equip_items))
    else:
        st.write(loc.msg_cannot_equip_martial)


def add_item_as(item: Item, inventory: Inventory, loc: LocNamespace):
    new_name = st.text_input(loc.page_equipment_write_new_name)
    button_label = loc.page_equipment_add_item_as_button.format(name=new_name)

    cannot_afford = inventory.zenit < item.cost
    if cannot_afford:
        st.warning(loc.error_not_enough_zenit.format(cost=item.cost, zenit=inventory.zenit), icon="💰")
    if st.button(button_label, disabled=not new_name or cannot_afford):
        item = deepcopy(item)
        item.name = new_name
        if isinstance(item, Armor):
            inventory.backpack.armors.append(item)
        elif isinstance(item, Weapon):
            inventory.backpack.weapons.append(item)
        elif isinstance(item, Shield):
            inventory.backpack.shields.append(item)
        else:
            st.error(loc.page_equipment_unknown_item_type)
            return
        st.toast(loc.page_equipment_added.format(name=new_name))
        inventory.zenit -= item.cost
        st.rerun()


def join_with_or(items, loc: LocNamespace):
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + loc.or_separator + items[-1]

def join_with_and(items, loc: LocNamespace):
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + loc.and_separator + items[-1]

def add_bond(controller: CharacterController, loc: LocNamespace):
    with st.expander(loc.bond_explanation):
        st.write(loc.msg_bond_explanation)
    name = st.text_input(loc.bond_name)

    col1, col2, col3 = st.columns(3)
    with col1:
        respect = st.pills(loc.bond_respect_description, [Emotion.admiration, Emotion.inferiority],
                           format_func=lambda s: s.localized_name(loc), selection_mode="single")
    with col2:
        trust = st.pills(loc.bond_trust_description, [Emotion.loyalty, Emotion.mistrust],
                           format_func=lambda s: s.localized_name(loc), selection_mode="single")
    with col3:
        affinity = st.pills(loc.bond_affinity_description, [Emotion.affection, Emotion.hatred],
                           format_func=lambda s: s.localized_name(loc), selection_mode="single")
    input_dict = {
        "name": name,
        "respect": respect,
        "trust": trust,
        "affinity": affinity,
    }

    can_add = any(input_dict.get(k) is not None for k in ["respect", "trust", "affinity"]) and (name != "")
    if not can_add:
        st.warning(loc.adding_bond_error)

    if st.button(loc.add_bond_button,
                 key="add-bond-button",
                 disabled=not can_add
    ):
        new_bond = Bond(
            **input_dict
        )
        controller.character.bonds.append(new_bond)
        st.rerun()

def remove_bond(controller: CharacterController, loc: LocNamespace):
    for i, bond in enumerate(controller.character.bonds):
        c1, c2 = st.columns([0.8, 0.2])
        with c1:
            st.write(f"**{bond.name}**")
            st.write(" | ".join(e.localized_name(loc) for e in [bond.respect, bond.trust, bond.affinity] if e is not None))
        with c2:
            if st.button(loc.remove_button, key=f"bond-{i}-remove"):
                del controller.character.bonds[i]
                st.rerun()


def upgrade_item(controller: CharacterController, item: Item, loc: LocNamespace):
    if item.quality == "no_quality":
        st.markdown(loc.page_view_upgrade_add_quality)
    else:
        st.markdown(loc.page_view_upgrade_replace_quality)

    available_qualities = []

    if isinstance(item, Weapon):
        available_qualities.extend(
            [q for q in c.COMPENDIUM.qualities["weapons"] if q.cost <= 1000]
        )
    else:
        available_qualities.extend(
            [q for q in c.COMPENDIUM.qualities["armors"] if q.cost <= 1000]
        )

    selected_quality, detail = select_quality(available_qualities, loc)

    cannot_afford = selected_quality is not None and not controller.can_afford(selected_quality.cost)
    if cannot_afford:
        st.warning(loc.error_not_enough_zenit.format(
            cost=selected_quality.cost, zenit=controller.character.inventory.zenit
        ), icon="💰")

    if st.button(
            loc.upgrade_button,
            key=f'{item.name}-upgrade-confirm',
            disabled=not selected_quality or cannot_afford,
    ):
        try:
            controller.upgrade_item(item, selected_quality, detail)
        except ValueError as e:
            st.error(str(e))
        else:
            st.rerun()


def select_quality(
        available_qualities: list[Quality],
        loc: LocNamespace
) -> (Quality, list[Status | DamageType | Species]):
    selected_quality: Quality | None = st.selectbox(
        "selected_quality",
        sorted(available_qualities, key=lambda x: x.localized_name(loc)),
        index=None,
        format_func=lambda x: x.localized_name(loc),
        label_visibility="hidden"
    )
    detail = list()

    if selected_quality:
        st.markdown(loc.page_view_upgrade_cost.format(cost=selected_quality.cost))
        st.markdown(selected_quality.localized_description(loc))
        match selected_quality.name:
            case "antistatus":
                detail = st.pills(
                    loc.page_view_select_status,
                    [status for status in Status],
                    format_func=lambda x: x.localized_name(loc),
                )
            case "status":
                detail = st.pills(
                    loc.page_view_select_status,
                    [Status.slow, Status.shaken, Status.dazed, Status.weak],
                    format_func=lambda x: x.localized_name(loc),
                )
            case "status_plus":
                detail = st.pills(
                    loc.page_view_select_status,
                    [Status.enraged, Status.poisoned],
                    format_func=lambda x: x.localized_name(loc),
                )
            case "resistance" | "immunity" | "damage_change":
                detail = st.pills(
                    loc.page_view_select_damage,
                    [dmg for dmg in DamageType if dmg.name not in ["no_damage", "physical", "no_type"]],
                    format_func=lambda x: x.localized_name(loc),
                )
            case "dual_resistance":
                detail = st.pills(
                    loc.page_view_select_damage,
                    [dmg for dmg in DamageType if dmg.name not in ["no_damage", "physical", "no_type"]],
                    format_func=lambda x: x.localized_name(loc),
                    selection_mode="multi",
                )
            case "hunter":
                detail = st.pills(
                    loc.page_view_select_species,
                    [species for species in Species],
                    format_func=lambda x: x.localized_name(loc),
                )
            case "dual_hunter":
                detail = st.pills(
                    loc.page_view_select_species,
                    [species for species in Species],
                    format_func=lambda x: x.localized_name(loc),
                    selection_mode="multi",
                )
    if not detail:
        detail = list()
    if not isinstance(detail, list):
        detail = [detail]
    return selected_quality, detail




def colored_attr(name, prefix, current, base):
    value = f"{prefix}{current}"
    if current > base:
        value = f":green[{value}]"
    elif current < base:
        value = f":red[{value}]"
    return f"**{name}**: {value}"


HP_BAR_COLOR = "#21a336"
MP_BAR_COLOR = "#1c83e1"
IP_BAR_COLOR = "#e8a317"


def resource_bar(label: str, current: int, maximum: int, color: str) -> str:
    """HTML for a labelled HP/MP/IP bar (render with unsafe_allow_html).
    Self-contained markup, so it doesn't rely on Streamlit's internal DOM;
    the label inherits the theme's text color."""
    fraction = min(max(current / maximum, 0), 1) if maximum else 0
    return (
        # Track: same height as Streamlit's inputs/buttons (2.5rem), so a
        # center-aligned row of bar + widgets lines up exactly. The 1rem bottom
        # margin cancels the -1rem that Streamlit puts on every st.markdown
        # element, which would otherwise shift the bar down when centred.
        "<div style='position:relative;height:2.5rem;margin-bottom:1rem;border-radius:0.5rem;"
        "background:rgba(128,128,128,0.2);overflow:hidden'>"
        # Fill: semi-transparent, so the text stays readable in light and dark themes.
        f"<div style='position:absolute;top:0;bottom:0;left:0;width:{fraction * 100:.1f}%;"
        f"background:{color};opacity:0.7'></div>"
        # Label on top, vertically centred inside the bar.
        "<div style='position:relative;height:100%;display:flex;align-items:center;"
        f"padding:0 0.75rem;font-weight:600'>{html.escape(str(label))} {current} / {maximum}</div>"
        "</div>"
    )


def _resolve_theme(stored: str, loc: LocNamespace) -> CharacterTheme | None:
    localizator = st.session_state.get("localizator")
    locs = localizator.all() if localizator else [loc]
    return CharacterTheme.from_stored(stored, locs)


def theme_options(stored: str, loc: LocNamespace) -> tuple[list[CharacterTheme], int | None]:
    """Theme choices for a selectbox (render with format_func=lambda t: t.localized_name(loc))
    and the index of the character's current theme, if it can be resolved."""
    options = list(CharacterTheme)
    theme = _resolve_theme(stored, loc)
    return options, (options.index(theme) if theme is not None else None)


def localized_theme(stored: str, loc: LocNamespace) -> str:
    """The character's theme in the current language; unrecognized text is shown as saved."""
    theme = _resolve_theme(stored, loc)
    return theme.localized_name(loc) if theme is not None else stored
