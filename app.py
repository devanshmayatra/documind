import streamlit as st
import tempfile
import os
import time
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlsplit

load_dotenv(override=True)

from core.ingestion import extract_chunks_with_metadata
from core.qdrant_engine import upload_chunks, qdrant, COLLECTION_NAME
from core.answer_service import answer_question
from core.answer_cache import AnswerCache, cache_failure

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
SOURCES = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))

st.set_page_config(
    page_title="F-1 Compass | UMD employment questions",
    page_icon=str(ASSETS / "compass.svg"),
    layout="wide",
    initial_sidebar_state="auto",
)
st.markdown(f"<style>{(ASSETS / 'compass.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

def get_db_stats():
    try:
        if qdrant.collection_exists(COLLECTION_NAME):
            col_info = qdrant.get_collection(COLLECTION_NAME)
            return col_info.points_count or 0
    except Exception:
        pass
    return None

def format_page_label(page):
    if page is None:
        return "Page Unavailable"
    return f"Page {page}"

def format_source_date(value):
    """Display an ISO date without inventing a date for missing metadata."""
    if not value:
        return "Unknown"
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except (TypeError, ValueError):
        return "Unknown"


def render_sources(passages):
    from html import escape

    if not passages:
        return

    with st.expander(f"Sources · {len(passages)} retrieved passages"):
        for index, passage in enumerate(passages, start=1):
            source = passage.get("source_title") or passage.get("source") or "Unknown source"
            publisher = passage.get("publisher") or "Publisher unavailable"
            with st.container(border=True):
                st.markdown(
                    f'<div class="source-heading"><span class="source-index">[S{index}]</span>'
                    f'<span>{escape(source)}</span></div>',
                    unsafe_allow_html=True,
                )
                st.caption(f"Publisher: {publisher}")
                st.caption(format_page_label(passage.get("page")))
                st.caption(f"Retrieved on: {format_source_date(passage.get('retrieved_at'))}")
                st.caption(f"Source updated: {format_source_date(passage.get('source_updated_at'))}")
                st.markdown(
                    f'<div class="source-excerpt">{escape(passage.get("text") or "")}</div>',
                    unsafe_allow_html=True,
                )
                url = (passage.get("source_url") or "").strip()
                try:
                    parsed = urlsplit(url)
                    valid_url = parsed.scheme in {"https", "http"} and bool(parsed.hostname)
                except ValueError:
                    valid_url = False
                if valid_url:
                    st.link_button("Read source", url)
                else:
                    st.caption("Source link unavailable")


def render_chat_message(message):
    with st.chat_message(message["role"]):
        st.caption("You" if message["role"] == "user" else "F-1 Compass")
        if message.get("cache_hit"):
            st.caption("Saved answer · original source passages retained")
        st.markdown(message["content"])
        render_sources(message.get("citations", []))


if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    mark = (ASSETS / "compass.svg").read_text(encoding="utf-8").replace("<svg ", '<svg class="brand-mark" aria-hidden="true" ')
    st.markdown(
        f'<div class="brand">{mark}<div><div class="brand-name">F-1 Compass</div>'
        '<div class="brand-note">A source-first starting point</div></div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="scope-label">Current coverage</p>'
        '<p class="scope-name">University of Maryland</p>'
        '<p class="scope-detail">College Park · F-1 employment</p>', unsafe_allow_html=True,
    )
    with st.expander("UMD ISSS sources"):
        for source in SOURCES.values():
            st.link_button(source["title"], source["source_url"], use_container_width=True)
    st.markdown(
        '<p class="sidebar-note">Read the source alongside the answer. For personal eligibility '
        'or authorization questions, contact UMD ISSS.</p>', unsafe_allow_html=True,
    )
    st.divider()

    # Enable only in a trusted operator instance, never on the public instance.
    ingestion_enabled = os.getenv("F1_COMPASS_ENABLE_INGESTION", "").lower() == "true"

    if ingestion_enabled:
        st.markdown("### Add source documents")
        uploaded_files = st.file_uploader(
            "Upload files to Knowledge Base",
            type=["pdf", "docx", "txt", "md"],
            accept_multiple_files=True,
            label_visibility="collapsed"
        )

        if st.button("Process and index", type="primary", use_container_width=True):
            if uploaded_files:
                total_chunks = 0
                prog_bar = st.progress(0, text="Reading documents...")
                for idx, file in enumerate(uploaded_files):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.name}") as tmp:
                        tmp.write(file.getvalue())
                        tmp_path = tmp.name

                    try:
                        chunks = extract_chunks_with_metadata(tmp_path, original_filename=file.name)
                        if chunks:
                            prog_bar.progress(
                                int(((idx + 0.5) / len(uploaded_files)) * 100),
                                text=f"Indexing {file.name}..."
                            )
                            upload_chunks(chunks)
                            total_chunks += len(chunks)
                    finally:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)

                prog_bar.progress(100, text="Indexing complete")
                time.sleep(0.4)
                prog_bar.empty()

                if total_chunks > 0:
                    st.success(f"Indexed {total_chunks} passages")
                else:
                    st.warning("No readable text found.")
            else:
                st.info("Upload at least one file first.")

    with st.expander("About this reference desk"):
        st.caption("Answers use passages from indexed UMD employment sources")
        points_count = get_db_stats()
        st.caption(f"{points_count:,} indexed passages" if points_count is not None else "Passage count unavailable")
        st.caption("A valid citation number does not establish that every claim is supported")
        if ingestion_enabled:
            st.caption("Gemini embeddings · BM42 hybrid search · FlashRank")

    if st.button("Start a new conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.pop("pending_prompt", None)
        st.session_state.pop("share_public_question", None)
        st.rerun()
    st.markdown('<p class="sidebar-note">No account needed<br>Your conversation resets on refresh</p>', unsafe_allow_html=True)
    with st.expander("Previously asked questions"):
        public_list = st.empty()

st.markdown(
    '<div class="workspace-bar"><span>UMD College Park / F-1 employment</span>'
    '<span>Questions, with sources</span></div>', unsafe_allow_html=True,
)

if not st.session_state.messages:
    st.markdown(
        '<div class="hero"><h1>Your F-1 employment questions<br><span class="hero-accent">A clearer starting point</span></h1>'
        '<p>Explore CPT, on-campus employment, and unpaid work at UMD, with the source passages '
        'there for you to read.</p></div>', unsafe_allow_html=True,
    )
    st.markdown('<p class="section-note">Not sure where to start?</p>', unsafe_allow_html=True)
    starters = [
        ("What belongs in a CPT offer letter?", "What must the UMD CPT employer offer letter include?"),
        ("What does remote work require?", "What does UMD require for documenting remote work in a CPT application?"),
        ("Which dates should the offer letter include?", "Does the UMD CPT offer letter need specific internship start and end dates?"),
        ("Is the CPT workshop required?", "Is workshop attendance required to apply for CPT?"),
    ]
    for row in range(0, len(starters), 2):
        for column, (label, question) in zip(st.columns(2), starters[row:row + 2]):
            with column:
                if st.button(label, key=f"starter_{row}_{label}", use_container_width=True):
                    st.session_state.pending_prompt = question
    st.markdown(
        '<div class="reading-note"><strong>Follow the citation</strong>'
        '<span>When source passages are available, open their numbered cards to check the '
        'wording, conditions, and available dates.</span></div>', unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div class="conversation-heading"><h1>Your F-1 employment questions</h1>'
        '<p>Keep the source in view as you explore the details</p></div>', unsafe_allow_html=True,
    )

for message in st.session_state.messages:
    render_chat_message(message)

use_shared_answers = st.checkbox(
    "Reuse and save answers to general questions", value=True,
    help="Turn this off to bypass saved answers. Only eligible first-turn questions are saved; matching ignores case and extra spaces, not differences in meaning.",
)
st.caption("General questions may be saved for reuse. Leave out names, document numbers, and personal details.")
share_publicly = False
if use_shared_answers and not st.session_state.messages:
    share_publicly = st.checkbox("Also show this question in the public list", value=False, key="share_public_question",
                                 help="Anyone can read the question text. Leave out personal details.")
prompt = st.chat_input("Ask about CPT, on-campus employment, or unpaid work")
if "pending_prompt" in st.session_state:
    prompt = st.session_state.pop("pending_prompt")

if prompt:
    user_message = {"role": "user", "content": prompt}
    st.session_state.messages.append(user_message)
    render_chat_message(user_message)

    with st.spinner("Finding the relevant passages and preparing an answer…"):
        try:
            response = answer_question(
                prompt, st.session_state.messages[:-1], allow_shared_cache=use_shared_answers,
                share_publicly=share_publicly,
            )
        except Exception:
            st.error("An answer could not be prepared right now. Try again later or consult UMD ISSS.")
            response = None
    if response is not None:
        result = response["result"]
        if result["citation_errors"]:
            print("[Citation check]", "; ".join(result["citation_errors"]))

        assistant_message = {
            "role": "assistant", "content": result["answer"],
            "citations": response["passages"], "generation_status": result["status"],
            "cache_hit": response["cache_hit"],
        }
        render_chat_message(assistant_message)
        st.session_state.messages.append(assistant_message)

with public_list.container():
    try:
        questions = AnswerCache().recent_questions()
    except (OSError, sqlite3.Error) as error:
        cache_failure(error)
        st.caption("Previously asked questions are temporarily unavailable.")
    else:
        if questions:
            with st.container(height=220):
                for question in questions:
                    st.text(question)
        else:
            st.caption("No questions have been shared publicly yet.")
