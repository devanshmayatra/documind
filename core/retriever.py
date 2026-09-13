from flashrank import Ranker, RerankRequest
from core.qdrant_engine import qdrant, get_dense_vector, get_sparse_vector, COLLECTION_NAME
from qdrant_client import models

ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")

def hybrid_search_and_rerank(query: str, initial_k: int = 15, final_k: int = 4):
    dense_vector = get_dense_vector(query)
    sparse_vector = get_sparse_vector(query)
    
    search_results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[
            models.Prefetch(query=dense_vector, using="dense", limit=initial_k),
            models.Prefetch(
                query=models.SparseVector(
                    indices=sparse_vector.indices.tolist(),
                    values=sparse_vector.values.tolist()
                ),
                using="sparse",
                limit=initial_k
            )
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=initial_k
    ).points
    
    if not search_results:
        return []
    
    passages = [
        {
            "id": p.id,
            "text": p.payload["text"],
            "source": p.payload["source"],
            "page": p.payload.get("page",1)
        }
        
        for p in search_results
    ]
    
    reranked = ranker.rerank(RerankRequest(query=query, passages=passages))
    return reranked[:final_k]