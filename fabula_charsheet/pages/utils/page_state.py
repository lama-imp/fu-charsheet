import streamlit as st

from pages.character_creation.creation_state import CreationState
from pages.character_view.view_state import ViewState
from typing import Callable


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
    "equipment_snapshot",
)


def reset_character_creation(message: str | None = None):
    """Start the wizard over for a new character; `message` is shown once
    as a toast on the next run."""
    for key in _CREATION_SESSION_KEYS:
        st.session_state.pop(key, None)
    if message:
        st.session_state.creation_flash = message
    st.rerun()


def wizard_nav(
        loc,
        back_to: CreationState | None = None,
        next_disabled: bool = False,
        on_back: Callable[[], None] | None = None,
        show_next: bool = True,
) -> bool:
    """Back / Next / Start over buttons for a creation step. Returns True when
    Next was clicked; Back (after running `on_back`) and a confirmed Start over
    navigate on their own."""

    @st.dialog(loc.page_start_over_dialog_title)
    def start_over_dialog():
        st.warning(loc.warn_confirm_start_over, icon="❓")
        c1, c2 = st.columns(2)
        with c1:
            if st.button(loc.no_button, key="start-over-no"):
                st.rerun()
        with c2:
            if st.button(loc.start_over_confirm_button, key="start-over-yes"):
                reset_character_creation()

    next_clicked = False
    back_col, next_col, reset_col = st.columns(3)
    with back_col:
        if back_to is not None and st.button(loc.back_button, icon=":material/arrow_back:", key="wizard-back"):
            if on_back is not None:
                on_back()
            set_creation_state(back_to)
    with next_col:
        if show_next:
            next_clicked = st.button(loc.page_next_button, disabled=next_disabled, key="wizard-next")
    with reset_col:
        if back_to is not None and st.button(loc.start_over_button, icon=":material/restart_alt:", key="wizard-start-over"):
            start_over_dialog()
    return next_clicked
