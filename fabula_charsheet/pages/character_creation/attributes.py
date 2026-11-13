import streamlit as st

from data.models import Dexterity, Might, Insight, Willpower, LocNamespace
from .creation_state import CreationState
from pages.utils import set_creation_state, wizard_nav
from config import BASE_ATTRIBUTE_SUM
from pages.controller import CharacterController


ATTRIBUTE_DIE_SIZES = [6, 8, 10, 12]


def _attribute_slider(controller: CharacterController, attribute: str, label: str) -> int:
    # Seed the slider from the character once, so it shows the saved value when
    # coming back to this step, without fighting the user's input on reruns.
    key = f"creation-attr-{attribute}"
    if key not in st.session_state:
        st.session_state[key] = getattr(controller.character, attribute).base
    return st.select_slider(label, options=ATTRIBUTE_DIE_SIZES, key=key)


def build(controller: CharacterController):
    loc: LocNamespace = st.session_state.localizator.get(st.session_state.language)
    st.title(loc.page_attributes_title)
    st.markdown(loc.page_attributes_message)
    dexterity = _attribute_slider(controller, "dexterity", loc.attr_dexterity)
    might = _attribute_slider(controller, "might", loc.attr_might)
    insight = _attribute_slider(controller, "insight", loc.attr_insight)
    willpower = _attribute_slider(controller, "willpower", loc.attr_willpower)
    not_ready_for_the_next_step = (sum([dexterity, might, insight, willpower]) != BASE_ATTRIBUTE_SUM)
    if not_ready_for_the_next_step:
        st.error(loc.page_attributes_sum_error, icon="🎲")
    try:
        controller.character.dexterity = Dexterity(base=dexterity, current=dexterity)
        controller.character.might = Might(base=might, current=might)
        controller.character.insight = Insight(base=insight, current=insight)
        controller.character.willpower = Willpower(base=willpower, current=willpower)
    except Exception as e:
        st.error(e, icon="🚨")

    if wizard_nav(loc, back_to=CreationState.classes, next_disabled=not_ready_for_the_next_step):
        set_creation_state(CreationState.equipment)
