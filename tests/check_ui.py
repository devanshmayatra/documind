"""Real Streamlit UI smoke check with the offline preview harness.

Run in the project environment: python -B tests/check_ui.py
"""
from pathlib import Path
from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
app = AppTest.from_file(str(ROOT / "tests/ui_preview.py")).run(timeout=30)
assert not app.exception, app.exception
assert not app.get("file_uploader"), "Public ingestion must remain hidden"
assert any(item.value == "What are UMD’s volunteer criteria?" for item in app.text)
assert app.checkbox[1].value is False, "Publishing must be opt-in"
assert len(app.button) == 5, "Four starter questions and a new-conversation button"

app.checkbox[0].uncheck().run()
assert not app.exception
assert app.checkbox[0].value is False

app.chat_input[0].set_value("Does the UMD CPT offer letter need specific internship start and end dates?").run()
assert not app.exception, app.exception
assert len(app.chat_message) == 2
captions = [caption.value for caption in app.caption]
assert "Retrieved on: 2026-11-14" in captions
assert "Source updated: Unknown" in captions
assert app.checkbox[0].value is False, "The visitor's cache preference must survive the chat rerun"
assert any("specific start and end dates" in block.value for block in app.markdown)

next(button for button in app.button if button.label == "Start a new conversation").click().run()
assert not app.exception
assert len(app.chat_message) == 0
for label, expected in (
    ("What belongs in a CPT offer letter?", "What must the UMD CPT employer offer letter include?"),
    ("What does remote work require?", "What does UMD require for documenting remote work in a CPT application?"),
    ("Which dates should the offer letter include?", "Does the UMD CPT offer letter need specific internship start and end dates?"),
    ("Is the CPT workshop required?", "Is workshop attendance required to apply for CPT?"),
):
    next(button for button in app.button if button.label == label).click().run()
    assert not app.exception
    assert app.session_state["messages"][0]["content"] == expected
    next(button for button in app.button if button.label == "Start a new conversation").click().run()
app.checkbox[0].check().run()
app.checkbox[1].check().run()
app.chat_input[0].set_value("What are the UMD volunteering criteria?").run()
next(button for button in app.button if button.label == "Start a new conversation").click().run()
assert app.checkbox[1].value is False, "Each new conversation starts with public sharing off"
print("PASS: real Streamlit empty state, public controls, cache opt-out, recorded chat, source dates, and conversation reset")
