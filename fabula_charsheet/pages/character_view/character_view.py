import streamlit as st

from . import loader, view
from .view_state import ViewState
from pages.controller import CharacterController


title_key = "page_title_character_view"
icon = ":material/file_open:"


def build():
    loc = st.session_state.localizator.get(st.session_state.language)
    st.session_state.view_step = st.session_state.get("view_step", ViewState.load)
    if "char_controller" not in st.session_state:
        st.session_state.char_controller = CharacterController(loc)
    # Keep the controller's messages in the currently selected language
    st.session_state.char_controller.loc = loc

    match st.session_state.view_step:
        case ViewState.load:
            loader.build(st.session_state.char_controller)
        case ViewState.view:
            view.build(st.session_state.char_controller)
