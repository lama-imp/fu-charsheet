import streamlit as st

from pages.character_creation.creation_state import CreationState
from pages.character_view.view_state import ViewState


def set_view_state(state: ViewState):
    st.session_state.view_step = state
    st.rerun()


def set_creation_state(state: CreationState):
    st.session_state.creation_step = state
    st.rerun()


# Everything the creation wizard keeps between steps. Cleared after a character
# is saved, so the next one starts from scratch (with a new id).
_CREATION_SESSION_KEYS = (
    "creation_controller",
    "creation_step",
    "avatar",
    "class_controller",
    "class_spells",
    "selected_hero_skills",
    "start_equipment",
    "additional_zenit",
)


def reset_character_creation(message: str | None = None):
    """Start the wizard over for a new character; `message` is shown once
    as a toast on the next run."""
    for key in _CREATION_SESSION_KEYS:
        st.session_state.pop(key, None)
    if message:
        st.session_state.creation_flash = message
    st.rerun()
