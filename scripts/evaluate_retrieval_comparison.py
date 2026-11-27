"""Compare three production retrieval paths against snapshot-derived evidence labels."""
from datetime import datetime, timezone
from pathlib import Path
import json
import logging

from qdrant_client import models

from core.answer_cache import source_manifest
from core.qdrant_engine import COLLECTION_NAME, get_dense_vector, qdrant
from core.retriever import retrieve_candidates, rerank_candidates
from scripts.eval_pacing import paced_cases


ROOT = Path(__file__).resolve().parents[1]
MODES = ("dense", "hybrid", "hybrid_reranked")


def indexed_snapshot(source_id, snapshot):
    points, offset = qdrant.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=models.Filter(must=[
            models.FieldCondition(key="source_id", match=models.MatchValue(value=source_id))
        ]),
        limit=100, with_payload=True, with_vectors=False,
    )
    if offset is not None:
        raise ValueError(f"Expected a single page of indexed passages for {source_id}")
    return {
        str(point.id): " ".join(point.payload["text"].casefold().split())
        for point in points
        if point.payload.get("source_content_sha256") == snapshot["content_sha256"]
        and point.payload.get("retrieved_at") == snapshot["retrieved_at"]
    }


def main():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cases = json.loads((ROOT / "evaluation/retrieval_comparison.json").read_text(encoding="utf-8"))
    all_snapshots = source_manifest()
    snapshots = {source: all_snapshots[source] for source in sorted({case["source"] for case in cases})}
    corpus = {source: indexed_snapshot(source, snap) for source, snap in snapshots.items()}
    for case in cases:
        points = corpus[case["source"]]
        case["evidence_ids"] = [
            sorted(point_id for point_id, passage in points.items()
                   if any(" ".join(phrase.casefold().split()) in passage for phrase in alternatives))
            for alternatives in case["evidence"]
        ]
        if not all(case["evidence_ids"]):
            raise ValueError(f"Unmatched evidence for {case['id']}: {case['evidence_ids']}")

    results = []
    for case in paced_cases(cases, default_delay=5):
        print(case["id"], flush=True)
        question = case["question"]
        row = dict(case)
        try:
            vector = get_dense_vector(question)
            dense = retrieve_candidates(question, mode="dense", dense_vector=vector)
            hybrid = retrieve_candidates(question, mode="hybrid", dense_vector=vector)
            reranked = rerank_candidates(question, hybrid)
            row["rankings"] = {
                mode: [str(passage["id"]) for passage in passages]
                for mode, passages in zip(MODES, (dense, hybrid, reranked))
            }
        except Exception as error:
            row["error"] = type(error).__name__
            code = getattr(error, "code", None)
            row["error_code"] = code if type(code) is int else None
            print(f"  {row['error']} ({row['error_code']})", flush=True)
        results.append(row)

    completed = [row for row in results if "rankings" in row]
    totals = {}
    for mode in MODES:
        counts = dict.fromkeys(("hit_at_1", "hit_at_5", "complete_at_4"), 0)
        for row in completed:
            ranking = row["rankings"][mode]
            groups = row["evidence_ids"]
            counts["hit_at_1"] += any(set(ranking[:1]).intersection(g) for g in groups)
            counts["hit_at_5"] += any(set(ranking[:5]).intersection(g) for g in groups)
            counts["complete_at_4"] += all(set(ranking[:4]).intersection(g) for g in groups)
        totals[mode] = counts
    report = {
        "collection": COLLECTION_NAME,
        "snapshots": {source: {"indexed_passages": len(corpus[source]),
                               "retrieved_at": snap["retrieved_at"],
                               "content_sha256": snap["content_sha256"]}
                      for source, snap in snapshots.items()},
        "initial_k": 15, "attempted": len(cases), "completed": len(completed),
        "totals": totals, "results": results,
    }
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / "evaluation/runs" / f"retrieval_comparison_{timestamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Completed {len(completed)}/{len(cases)}")
    print(json.dumps(totals, indent=2))
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
