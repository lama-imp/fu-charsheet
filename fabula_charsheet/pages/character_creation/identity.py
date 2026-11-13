import streamlit as st

from .creation_state import CreationState
from pages.utils import set_creation_state, theme_options, wizard_nav
from pages.controller import CharacterController
from data.models import LocNamespace


def build(controller: CharacterController):
    loc: LocNamespace = st.session_state.localizator.get(st.session_state.language)
    character = controller.character

    st.title(loc.page_identity_character_info_title)

    # Pre-filled from the character, so coming back with "Back" keeps what was entered.
    character_name = st.text_input(loc.page_identity_character_name_label, value=character.name)
    character_level = st.number_input(
        loc.page_identity_character_level_label, value=character.level, min_value=1, max_value=60
    )
    identity = st.text_input(loc.page_identity_identity_label, value=character.identity)
    origin = st.text_input(loc.page_identity_origin_label, value=character.origin)
    theme_list, theme_idx = theme_options(character.theme, loc)
    theme = st.selectbox(
        loc.page_identity_theme_label,
        theme_list,
        format_func=lambda t: t.localized_name(loc),
        index=theme_idx,
        placeholder=loc.page_identity_theme_placeholder,
        accept_new_options=False,
    )

    # Validate only when the user tries to move on, not before they've typed anything.
    if wizard_nav(loc):
        try:
            character.set_name(character_name, loc)
            character.set_level(character_level, loc)
            character.set_identity(identity, loc)
            character.set_origin(origin, loc)
            character.set_theme(theme, loc)
        except Exception as e:
            st.warning(e, icon="🤌")
        else:
            set_creation_state(CreationState.classes)
