import pytest

from pages.utils import page_state


class Rerun(Exception):
    pass


def test_reset_character_creation_clears_wizard_state(streamlit_stub, monkeypatch):
    def rerun():
        raise Rerun

    monkeypatch.setattr(streamlit_stub, "rerun", rerun, raising=False)
    session = streamlit_stub.session_state
    for key in page_state._CREATION_SESSION_KEYS:
        session[key] = object()
    session["language"] = "en"  # unrelated state survives

    with pytest.raises(Rerun):
        page_state.reset_character_creation("saved!")

    assert not any(key in session for key in page_state._CREATION_SESSION_KEYS)
    assert session["creation_flash"] == "saved!"
    assert session["language"] == "en"
