# ⚡ DocuMind AI: Enterprise Multi-Document RAG

> **Live Demo:** Explore the deployed application at [https://documind-v1.streamlit.app/](https://documind-v1.streamlit.app/)

DocuMind AI is an enterprise-ready Retrieval-Augmented Generation (RAG) assistant designed for document intelligence and contextual question answering across multi-format file collections. It features a dual-vector hybrid search engine hosted on Qdrant Cloud, local FlashRank cross-encoder reranking, and real-time streaming powered by Google Gemini 3.6 Flash.

---

## 📸 Key Features

* **Multi-Format Ingestion:** Seamlessly parses PDF, DOCX, TXT, and Markdown files with preserved document metadata (filename, page numbers).
* **Dual-Vector Hybrid Search:** Combines semantic dense vectors (`gemini-embedding-001`) with lexical sparse vectors (BM42 via `FastEmbed`) within a unified Qdrant Cloud collection.
* **Cross-Encoder Reranking:** Employs `FlashRank` to rerank top retrieved candidate chunks before context injection, filtering out noise and maximizing retrieval precision.
* **Contextual Query Reformulation:** Resolves conversational pronouns and multi-turn context dependencies into standalone search queries.
* **Real-Time Token Streaming:** Streams response tokens directly from Gemini Flash for low-latency feedback.
* **Verifiable Citations:** Displays interactive citation cards complete with source document names, page numbers, text snippets, and rerank confidence scores.
* **Production-Grade UI:** Engineered in Streamlit with fixed-dimension sidebars, live Qdrant Cloud cluster telemetry, and dark-mode styling.

---

## 🏗️ Architecture Pipeline

```text
[User Document Upload] (PDF, DOCX, TXT, MD)
         │
         ▼
[Text Chunking & Metadata Extraction]
         │
         ├───► Dense Embeddings (Gemini-Embedding-001)
         └───► Sparse Embeddings (FastEmbed BM42)
                   │
                   ▼
     [Qdrant Cloud Managed Cluster]
                   ▲
                   │ Hybrid Search (Dense + Sparse Fusion)
                   │
[User Prompt] ──► [Query Rewriter] ──► [FlashRank Cross-Encoder]
                                              │
                                              ▼
                                   [Top Reranked Passages]
                                              │
                                              ▼
                              [Gemini 3.6 Flash Streaming Engine]
                                              │
                                              ▼
                                 [Grounded Answer + Citations]

```

---

## 🛠️ Tech Stack

* **Frontend Framework:** Streamlit
* **Vector Database:** Qdrant Cloud (Managed Vector DB)
* **Language Model:** Google Gemini 3.6 Flash via `google-genai` SDK
* **Dense Embeddings:** Gemini Embedding (`models/gemini-embedding-001`)
* **Sparse Embeddings:** FastEmbed (`Qdrant/bm42-all-minilm-l6-v2-attentions`)
* **Reranker:** FlashRank Cross-Encoder (`ms-marco-TinyBERT-L-2-v2`)
* **Document Processing:** PyPDF, python-docx, LangChain Text Splitters

---

## 📂 Project Structure

```text
documind/
├── app.py                   # Streamlit interface, session state & streaming logic
├── core/
│   ├── __init__.py
│   ├── ingestion.py         # Multi-format document parsers & text splitters
│   ├── qdrant_engine.py     # Qdrant Cloud client, schema setup & batched indexing
│   ├── retriever.py         # Hybrid retrieval & FlashRank reranker
│   └── generator.py         # Query rewriting & Gemini client integration
├── requirements.txt         # Pinned project dependencies
├── .env.example             # Environment variable template
├── .streamlit/
│   └── config.toml          # Server polling & layout configuration
└── README.md

```

---

## 🚀 Getting Started

### Prerequisites

* Python 3.10+
* Conda or `venv`
* [Google AI Studio API Key](https://aistudio.google.com/app/apikey)
* [Qdrant Cloud Cluster](https://cloud.qdrant.io/) (Cluster URL & API Key)

### 1. Clone & Environment Setup

```bash
git clone git@github.com:devanshmayatra/documind.git
cd documind

conda create -n doc-rag python=3.11 -y
conda activate doc-rag
pip install -r requirements.txt

```

### 2. Environment Variables

Create a `.env` file in the root directory:

```bash
cat << 'EOF' > .env
GEMINI_API_KEY=your_actual_gemini_api_key_here
QDRANT_URL=https://your-cluster-url.qdrant.io:6333
QDRANT_API_KEY=your_qdrant_api_key_here
EOF

```

### 3. Run Locally

Run the application with polling enabled for live updates:

```bash
streamlit run app.py --server.fileWatcherType poll --server.runOnSave true

```

Access the app in your browser at `http://localhost:8501`.

---

## 🌐 Cloud Deployment (Streamlit Community Cloud)

1. Push your repository to GitHub (`devanshmayatra/documind`).
2. Go to [share.streamlit.io](https://share.streamlit.io) and create a **New app**.
3. Select `devanshmayatra/documind`, branch `main`, and set **Main file path** to `app.py`.
4. Under **Advanced Settings > Secrets**, add your Qdrant Cloud and Gemini credentials in TOML format:

```toml
GEMINI_API_KEY = "AIzaSy..."
QDRANT_URL = "https://your-cluster-url.aws.cloud.qdrant.io:6333"
QDRANT_API_KEY = "your-qdrant-cloud-api-key"

```

5. Click **Deploy**. Access the production application at [https://documind-v1.streamlit.app/](https://documind-v1.streamlit.app/).

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](https://www.google.com/search?q=LICENSE) file for details.
