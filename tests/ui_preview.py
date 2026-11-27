"""Offline Streamlit design harness; never use this entry point for deployment.

Run with: streamlit run tests/ui_preview.py --server.port 8502
It renders the real app, with recorded development data instead of live calls.
"""
import json
from pathlib import Path
import runpy
import sys
from types import ModuleType, SimpleNamespace

import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
report = json.loads((ROOT / "evaluation/runs/end_to_end_20261115T142328883386Z.json")
                    .read_text(encoding="utf-8"))
recorded = next(row for row in report["results"] if row["case_id"] == "offer_letter_explicit_dates")


def recorded_answer(question, history, allow_shared_cache=True, share_publicly=False):
    return {
        "query": recorded["question"], "passages": recorded["passages"],
        "cache_hit": False,
        "result": {"answer": recorded["answer"], "status": recorded["actual_status"], "citation_errors": []},
    }


replacements = {
    "core.answer_cache": {
        "AnswerCache": lambda: SimpleNamespace(recent_questions=lambda: ["What are UMD’s volunteer criteria?"]),
        "cache_failure": lambda error: None,
    },
    "dotenv": {"load_dotenv": lambda **kwargs: False},
    "core.ingestion": {"extract_chunks_with_metadata": lambda *args, **kwargs: []},
    "core.qdrant_engine": {
        "COLLECTION_NAME": "offline_preview",
        "qdrant": SimpleNamespace(collection_exists=lambda name: False),
        "upload_chunks": lambda *args, **kwargs: None,
    },
    "core.answer_service": {"answer_question": recorded_answer},
}
for name, attributes in replacements.items():
    module = ModuleType(name)
    module.__dict__.update(attributes)
    sys.modules[name] = module

st.caption("Offline design preview · recorded development answer · no live API calls")
runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
