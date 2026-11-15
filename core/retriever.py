from flashrank import Ranker, RerankRequest
from qdrant_client import models

from core.qdrant_engine import (
    COLLECTION_NAME,
    get_dense_vector,
    get_sparse_vector,
    qdrant,
)


ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")


def retrieve_candidates(
    query: str,
    mode: str = "hybrid",
    initial_k: int = 15,
):
    """Retrieve candidates without reranking."""
    if mode not in {"dense", "sparse", "hybrid"}:
        raise ValueError(f"Unsupported retrieval mode: {mode}")

    if initial_k < 1:
        raise ValueError("initial_k must be positive.")

    query_options = {}

    if mode in {"dense", "hybrid"}:
        dense_vector = get_dense_vector(query)

    if mode in {"sparse", "hybrid"}:
        sparse_embedding = get_sparse_vector(query)
        sparse_vector = models.SparseVector(
            indices=sparse_embedding.indices.tolist(),
            values=sparse_embedding.values.tolist(),
        )

    if mode == "dense":
        query_options = {
            "query": dense_vector,
            "using": "dense",
        }

    elif mode == "sparse":
        query_options = {
            "query": sparse_vector,
            "using": "sparse",
        }

    else:
        query_options = {
            "prefetch": [
                models.Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=initial_k,
                ),
                models.Prefetch(
                    query=sparse_vector,
                    using="sparse",
                    limit=initial_k,
                ),
            ],
            "query": models.FusionQuery(fusion=models.Fusion.RRF),
        }

    search_results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        limit=initial_k,
        with_payload=True,
        with_vectors=False,
        **query_options,
    ).points

    return [
        {
            "id": point.id,
            "text": point.payload["text"],
            "source": point.payload["source"],
            "page": point.payload.get("page"),
            "source_url": point.payload.get("source_url"),
            "publisher": point.payload.get("publisher"),
            "source_title": point.payload.get("source_title"),
            "retrieved_at": point.payload.get("retrieved_at"),
            "source_updated_at": point.payload.get("source_updated_at"),
        }
        for point in search_results
    ]


def rerank_candidates(query: str, candidates: list[dict]):
    """Rerank copies so the original candidate order stays intact."""
    if not candidates:
        return []

    return ranker.rerank(
        RerankRequest(
            query=query,
            passages=[dict(passage) for passage in candidates],
        )
    )


def diagnose_hybrid_retrieval(query: str, initial_k: int = 15):
    """Return hybrid candidates and their full reranked order."""
    candidates = retrieve_candidates(
        query,
        mode="hybrid",
        initial_k=initial_k,
    )

    return {
        "candidates": candidates,
        "reranked": rerank_candidates(query, candidates),
    }


def hybrid_search_and_rerank(
    query: str,
    initial_k: int = 15,
    final_k: int = 4,
):
    results = diagnose_hybrid_retrieval(query, initial_k)
    return results["reranked"][:final_k]
