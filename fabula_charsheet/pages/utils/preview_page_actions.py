from copy import deepcopy

import streamlit as st

from pages.utils import SkillTableWriter, if_show_spells, SpellTableWriter, show_skill, theme_options
from config import BASE_ATTRIBUTE_SUM
from pages.controller import CharacterController, ClassController
from data.models import Dexterity, Might, Insight, Willpower, Item, CharClass, LocNamespace
from data import compendium as c


def equip_item(controller, item: Item):
    try:
        controller.equip_item(item)
    except Exception as e:
        st.warning(e, icon="🙅‍♂️")


def unequip_item(controller, category: str):
    try:
        controller.unequip_item(category)
    except Exception as e:
        st.warning(e)


def disable_equip_button(controller, item: Item) -> bool:
    return controller.is_equipped(item)


def avatar_uploader(loc: LocNamespace):
    uploaded_avatar = st.file_uploader(
        loc.msg_upload_avatar,
        accept_multiple_files=False,
        type=["jpg", "jpeg", "png", "gif"],
        label_visibility="hidden"
    )
    if uploaded_avatar is not None:
        st.image(uploaded_avatar, width=100)
    if st.button(loc.use_avatar_button, disabled=not uploaded_avatar):
        st.session_state.avatar = uploaded_avatar
        st.rerun()


def edit_identity(controller: CharacterController, loc: LocNamespace):
    character_name = st.text_input(loc.page_identity_character_name_label, value=controller.character.name)
    identity = st.text_input(loc.page_identity_identity_label, value=controller.character.identity)
    origin = st.text_input(loc.page_identity_origin_label, value=controller.character.origin)
    options, default_theme_idx = theme_options(controller.character.theme, loc)
    theme = st.selectbox(
        loc.page_identity_theme_label,
        options,
        format_func=lambda t: t.localized_name(loc),
        index=default_theme_idx,
        placeholder=loc.page_identity_theme_placeholder,
        accept_new_options=False,
    )
    if st.button(loc.update_button):
        try:
            controller.character.set_name(character_name, loc)
            controller.character.set_identity(identity, loc)
            controller.character.set_origin(origin, loc)
            controller.character.set_theme(theme, loc)
            st.rerun()
        except Exception as e:
            st.warning(e, icon="🤌")


def edit_attributes(controller: CharacterController, loc: LocNamespace):
    dexterity = st.select_slider(
        loc.attr_dexterity,
        options=[6, 8, 10, 12],
        value=controller.character.dexterity.base,
    )
    might = st.select_slider(
        loc.attr_might,
        options=[6, 8, 10, 12],
        value=controller.character.might.base,
    )
    insight = st.select_slider(
        loc.attr_insight,
        options=[6, 8, 10, 12],
        value=controller.character.insight.base,
    )
    willpower = st.select_slider(
        loc.attr_willpower,
        options=[6, 8, 10, 12],
        value=controller.character.willpower.base,
    )
    attributes_error = (sum([dexterity, might, insight, willpower]) != BASE_ATTRIBUTE_SUM)
    if attributes_error:
        st.warning(loc.page_attributes_sum_error, icon="🎲")
    if st.button(loc.attributes_update_button, disabled=attributes_error):
        try:
            controller.character.dexterity = Dexterity(base=dexterity, current=dexterity)
            controller.character.might = Might(base=might, current=might)
            controller.character.insight = Insight(base=insight, current=insight)
            controller.character.willpower = Willpower(base=willpower, current=willpower)
            st.rerun()
        except Exception as e:
            st.error(e, icon="🚨")


def edit_class(character_controller: CharacterController, char_class: CharClass, loc: LocNamespace):
    class_controller = ClassController()
    class_controller.char_class = deepcopy(char_class)
    casting_skill = class_controller.char_class.get_spell_skill()
    # Work on a copy, so closing the dialog without saving changes nothing.
    st.session_state.class_spells = list(character_controller.character.spells.get(char_class.name, []))

    with st.expander(loc.page_class_choose_skills_expander):
        SkillTableWriter(loc).write_in_columns(class_controller.char_class.skills)

    # Counted with the edited skill levels, not the ones before the edit.
    skill_points_left = character_controller.skill_points_left_with(class_controller.char_class)

    if class_controller.char_class.class_level() < 1:
        class_not_ready = True
        st.error(loc.error_class_need_skill)
    elif skill_points_left < 0:
        st.error(loc.error_class_remove_skill.format(levels=abs(skill_points_left)))
        class_not_ready = True
    else:
        st.write(loc.msg_skills_selected)
        for skill in class_controller.char_class.skills:
            if skill.current_level > 0:
                show_skill(skill, loc)
        class_not_ready = False

    if if_show_spells(casting_skill):
        class_spells = c.COMPENDIUM.spells.get_spells(class_controller.char_class.name)
        with st.expander(loc.page_class_select_spells_expander):
            SpellTableWriter(loc).write_in_columns(class_spells)
        total_class_spells = len(st.session_state["class_spells"])
        max_n_spells = casting_skill.current_level

        if total_class_spells != max_n_spells:
            class_not_ready = True
            st.error(loc.error_class_select_exact_spells.format(max_n_spells=max_n_spells, casting_skill=casting_skill.localized_name(loc)))

    if st.button(loc.update_class_button, disabled=class_not_ready):
        try:
            character_controller.update_class(class_controller.char_class)
            if if_show_spells(casting_skill):
                character_controller.character.spells[char_class.name] = list(st.session_state.class_spells)
            else:
                character_controller.character.spells.pop(char_class.name, None)
            st.session_state.class_spells = []
            st.toast(loc.msg_class_updated.format(class_name=char_class.name.localized_name(loc)))
            st.rerun()
        except Exception as e:
            st.error(e, icon="🚨")
