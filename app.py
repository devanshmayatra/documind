import streamlit as st
import tempfile
import os
import time
from dotenv import load_dotenv

load_dotenv(override=True)

from core.ingestion import extract_chunks_with_metadata
from core.qdrant_engine import upload_chunks, qdrant, COLLECTION_NAME
from core.retriever import hybrid_search_and_rerank
from core.generator import rewrite_query, ai_client

# Page Config
st.set_page_config(
    page_title="DocuMind AI | Enterprise RAG",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS: Fixed Width Sidebar, Compact Uploader, Modern Badges & Metrics
st.markdown("""
<style>
    /* 1. Lock sidebar width & prevent scaling */
    [data-testid="stSidebar"] {
        min-width: 330px !important;
        max-width: 330px !important;
        width: 330px !important;
    }
    /* Hide drag resize handle */
    [data-testid="stSidebarResizerRoot"],
    div[data-testid="stSidebar"] > div:first-child > div:last-child {
        display: none !important;
    }

    /* 2. Sleek Badges */
    .badge-container {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 8px;
        margin-bottom: 4px;
    }
    .badge-pill {
        display: inline-flex;
        align-items: center;
        padding: 3px 9px;
        border-radius: 6px;
        font-size: 0.72rem;
        font-weight: 500;
        background-color: rgba(255, 255, 255, 0.07);
        border: 1px solid rgba(255, 255, 255, 0.12);
        color: #d1d5db;
        letter-spacing: 0.2px;
    }

    /* 3. Compact File Uploader */
    [data-testid="stFileUploader"] {
        padding-top: 0rem;
    }
    [data-testid="stFileUploaderDropzone"] {
        padding: 10px 14px !important;
        border-radius: 8px !important;
        min-height: unset !important;
    }
    [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {
        padding: 2px 10px !important;
        font-size: 0.8rem !important;
    }

    /* 4. Organized Metrics Card */
    .stats-card {
        background-color: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        padding: 12px 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-top: 8px;
    }
    .stat-box {
        display: flex;
        flex-direction: column;
    }
    .stat-label {
        font-size: 0.72rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 600;
    }
    .stat-val {
        font-size: 1.25rem;
        font-weight: 700;
        color: #f3f4f6;
        margin-top: 2px;
    }
    .status-indicator {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 0.88rem;
        font-weight: 600;
        color: #10b981;
    }
    .status-dot {
        width: 8px;
        height: 8px;
        background-color: #10b981;
        border-radius: 50%;
        box-shadow: 0 0 8px rgba(16, 185, 129, 0.6);
    }

    /* 5. Typography and Citation Card */
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        letter-spacing: -0.5px;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #888888;
        margin-bottom: 1.5rem;
    }
    .citation-card {
        border-left: 3px solid #ef4444;
        padding-left: 12px;
        margin-top: 8px;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

# Helper: Get current Qdrant collection stats
def get_db_stats():
    try:
        if qdrant.collection_exists(COLLECTION_NAME):
            col_info = qdrant.get_collection(COLLECTION_NAME)
            return col_info.points_count or 0
    except Exception:
        pass
    return 0

# Sidebar Implementation
with st.sidebar:
    st.markdown("### 🧠 DocuMind Engine")
    st.markdown("""
    <div class="badge-container">
        <span class="badge-pill">Dense: Gemini-001</span>
        <span class="badge-pill">Sparse: BM42</span>
        <span class="badge-pill">Rerank: FlashRank</span>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()

    st.markdown("#### 📁 Ingest Documents")
    uploaded_files = st.file_uploader(
        "Upload files to Knowledge Base",
        type=["pdf", "docx", "txt", "md"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    if st.button("⚡ Process & Index", type="primary", use_container_width=True):
        if uploaded_files:
            total_chunks = 0
            prog_bar = st.progress(0, text="Reading documents...")
            for idx, file in enumerate(uploaded_files):
                with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.name}") as tmp:
                    tmp.write(file.getvalue())
                    tmp_path = tmp.name

                try:
                    chunks = extract_chunks_with_metadata(tmp_path)
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

            prog_bar.progress(100, text="Done!")
            time.sleep(0.4)
            prog_bar.empty()
            
            if total_chunks > 0:
                st.success(f"Indexed **{total_chunks}** chunks!", icon="✅")
            else:
                st.warning("No readable text found.")
        else:
            st.info("Upload at least one file first.")

    st.divider()

    # Organized KB Stats Card
    st.markdown("#### 📊 Knowledge Base Stats")
    points_count = get_db_stats()
    st.markdown(f"""
    <div class="stats-card">
        <div class="stat-box">
            <span class="stat-label">Indexed Chunks</span>
            <span class="stat-val">{points_count}</span>
        </div>
        <div class="stat-box" style="align-items: flex-end;">
            <span class="stat-label">Cluster Status</span>
            <span class="status-indicator" style="margin-top: 4px;">
                <span class="status-dot"></span> Active
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# Main Header
st.markdown('<div class="main-header">Enterprise Knowledge Retrieval</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Multi-format RAG pipeline with hybrid search & cross-encoder reranking.</div>', unsafe_allow_html=True)

# Session State Initialization
if "messages" not in st.session_state:
    st.session_state.messages = []

# Empty State / Quick Starter Prompts
if not st.session_state.messages:
    st.info("💡 **Getting started:** Upload your documents in the left sidebar, click **Process & Index**, and start querying below.")
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📌 Summarize key topics in the documents", use_container_width=True):
            st.session_state.pending_prompt = "Summarize the key topics and takeaways across all indexed documents."
    with col_b:
        if st.button("🔍 Identify actionable recommendations", use_container_width=True):
            st.session_state.pending_prompt = "What are the primary actionable recommendations mentioned in the files?"

# Render Existing Conversation History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "citations" in msg and msg["citations"]:
            with st.expander(f"📚 View {len(msg['citations'])} Verified Sources"):
                for cit in msg["citations"]:
                    st.markdown(
                        f"""
                        <div class="citation-card">
                            <strong>{cit['source']}</strong> &nbsp;|&nbsp; Page {cit['page']} &nbsp;|&nbsp; 
                            <code>Score: {cit['score']:.3f}</code><br>
                            <span style="color:#555; font-size:0.9rem;">"{cit['text'][:280]}..."</span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

# Process Prompt (from chat_input or starter buttons)
prompt = st.chat_input("Ask a question about your documents...")
if "pending_prompt" in st.session_state:
    prompt = st.session_state.pop("pending_prompt")

if prompt:
    # 1. Render User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Contextual Query Rewriting & Retrieval
    with st.status("🔍 Retrieving verified passages...", expanded=False) as status:
        standalone_query = rewrite_query(prompt, st.session_state.messages[:-1])
        st.write(f"Refined search query: `{standalone_query}`")
        top_passages = hybrid_search_and_rerank(standalone_query)
        status.update(label="Relevant sources retrieved & reranked!", state="complete")

    # 3. Formulate Grounded Instruction
    context_blocks = "\n\n".join(
        [f"[Source: {p['source']} (Page {p['page']})]\n{p['text']}" for p in top_passages]
    )
    system_instruction = (
        "You are an enterprise knowledge retrieval agent. Answer using solely the excerpts provided below. "
        "Keep answers concise, direct, and well-structured using bullet points where appropriate. "
        "Cite the document name and page number for key facts. If the information is not present, "
        "state that the knowledge base does not contain the answer.\n\n"
        f"Context:\n{context_blocks}"
    )

    # 4. Stream Assistant Generation
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        # Real-time token streaming
        stream = ai_client.models.generate_content_stream(
            model="models/gemini-3.6-flash",
            contents=f"{system_instruction}\n\nQuestion: {prompt}"
        )
        for chunk in stream:
            if chunk.text:
                full_response += chunk.text
                response_placeholder.markdown(full_response + "▌")
        
        response_placeholder.markdown(full_response)

        # 5. Render Expandable Citations
        if top_passages:
            with st.expander(f"📚 View {len(top_passages)} Verified Sources"):
                for p in top_passages:
                    st.markdown(
                        f"""
                        <div class="citation-card">
                            <strong>{p['source']}</strong> &nbsp;|&nbsp; Page {p['page']} &nbsp;|&nbsp; 
                            <code>Score: {p['score']:.3f}</code><br>
                            <span style="color:#555; font-size:0.9rem;">"{p['text'][:280]}..."</span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

    # Save to history
    st.session_state.messages.append({
        "role": "assistant",
        "content": full_response,
        "citations": top_passages
    })