import os
import time
import uuid
from dotenv import load_dotenv
from google import genai
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models

load_dotenv(override=True)

raw_key = os.getenv("GEMINI_API_KEY", "")
GEMINI_API_KEY = raw_key.strip().strip("'").strip('"')

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing in environment or .env file.")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None

ai_client = genai.Client(api_key=GEMINI_API_KEY)
sparse_model = SparseTextEmbedding(model_name="Qdrant/bm42-all-minilm-l6-v2-attentions")
qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

COLLECTION_NAME = "resume_rag_kb"
EMBEDDING_MODEL = "models/gemini-embedding-001"
EMBEDDING_DIM = 3072


def ensure_source_id_index(payload_schema):
    """Add the source filter index without replacing an existing index."""
    existing = payload_schema.get("source_id")
    if existing is not None:
        if existing.data_type != models.PayloadSchemaType.KEYWORD:
            raise ValueError(
                f"Collection '{COLLECTION_NAME}' has a non-keyword source_id index. "
                "Existing index and data were preserved."
            )
        return

    qdrant.create_payload_index(
        collection_name=COLLECTION_NAME,
        field_name="source_id",
        field_schema=models.PayloadSchemaType.KEYWORD,
        wait=True,
    )


def setup_collection():
    """Ensure collection compatibility and its source index; preserve existing data."""
    
    if qdrant.collection_exists(COLLECTION_NAME):
        info = qdrant.get_collection(COLLECTION_NAME)
        vectors_config = info.config.params.vectors
        
        if not isinstance(vectors_config, dict) or "dense" not in vectors_config:
            raise ValueError(
                f"Collection '{COLLECTION_NAME}' is missing the expected"
                "'dense' vector configuration. Existing configuration was preserved."
            )
        
        dense_config = vectors_config["dense"]
        
        if dense_config.size != EMBEDDING_DIM:
            raise ValueError(
                f"Collection '{COLLECTION_NAME}' uses vectors with "
                f"{dense_config.size} dimensions, but this application "
                f"expects {EMBEDDING_DIM}. Existing data was preserved."
            )
        
        ensure_source_id_index(info.payload_schema)
        return
    
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense":models.VectorParams(
                size=EMBEDDING_DIM,
                distance=models.Distance.COSINE
            )
        },
        sparse_vectors_config={
            "sparse":models.SparseVectorParams(
                modifier=models.Modifier.IDF
            )
        },
    )
    ensure_source_id_index({})

def get_dense_vector(text: str) -> list[float]:
    """Retrieves dense embedding for a single string (used during user query retrieval)."""
    res = ai_client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
    return res.embeddings[0].values

def get_sparse_vector(text: str):
    """Generates sparse BM42 vector representation for lexical search."""
    return list(sparse_model.embed([text]))[0]


import time
import uuid
import re
from google import genai
from qdrant_client import models

def get_dense_embeddings_batch(texts: list[str], max_retries: int = 5) -> list[list[float]]:
    """Retrieves dense embeddings in batches with automatic rate-limit backoff."""
    if not texts:
        return []

    for attempt in range(max_retries):
        try:
            res = ai_client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=texts
            )
            return [e.values for e in res.embeddings]
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait_time = 15
                match = re.search(r"retry in (\d+(\.\d+)?)s", err_str)
                if match:
                    wait_time = int(float(match.group(1))) + 2
                
                print(f"[Rate-Limit] Quota reached. Cooling down for {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
            else:
                raise e

    raise RuntimeError("Failed to generate embeddings after multiple retry attempts due to quota limits.")


def upload_chunks(chunks: list[dict], batch_size: int = 10):
    if not chunks:
        return

    setup_collection()

    valid_chunks = [c for c in chunks if c.get("text", "").strip()]
    if not valid_chunks:
        return

    points = []

    for i in range(0, len(valid_chunks), batch_size):
        batch = valid_chunks[i : i + batch_size]
        batch_texts = [item["text"] for item in batch]

        dense_vectors = get_dense_embeddings_batch(batch_texts)

        sparse_vectors = list(sparse_model.embed(batch_texts))

        for item, d_vec, s_vec in zip(batch, dense_vectors, sparse_vectors):
            points.append(
                models.PointStruct(
                    id=item.get("chunk_id") or str(uuid.uuid4()),
                    vector={
                        "dense": d_vec,
                        "sparse": models.SparseVector(
                            indices=s_vec.indices.tolist(),
                            values=s_vec.values.tolist(),
                        ),
                    },
                    payload=item,
                )
            )

        time.sleep(3.0)

    # Upsert to Qdrant
    if points:
        for i in range(0, len(points), 100):
            qdrant.upsert(collection_name=COLLECTION_NAME, points=points[i : i + 100], wait=True)
