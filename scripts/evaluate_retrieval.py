import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import argparse

from core.retriever import hybrid_search_and_rerank


ROOT = Path(__file__).resolve().parents[1]


def main():
    
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split",
        choices=["development", "held_out"],
        default="development",
    )
    
    args = parser.parse_args()
    
    cases = json.loads(
        (ROOT / "evaluation" / "cases.json").read_text(
            encoding="utf-8"
        )
    )
    
    missing_split = [
        case["id"] for case in cases if "split" not in case
    ]
    if missing_split:
        raise ValueError(
            f"Cases missing a split: {missing_split}"
        )

    cases = [
        case for case in cases
        if case["split"] == args.split
    ]

    if not cases:
        raise ValueError(f"No cases found for split: {args.split}")

    print(f"Split: {args.split} | Cases: {len(cases)}")

    results = []

    for case in cases:
        print(f"Running: {case['id']}", flush=True)
        started = perf_counter()

        try:
            passages = hybrid_search_and_rerank(
                case["question"],
                initial_k=15,
                final_k=5,
            )

            result = {
                "case_id": case["id"],
                "question": case["question"],
                "status": "ok",
                "latency_seconds": perf_counter() - started,
                "passages": [
                    {
                        "rank": rank,
                        "point_id": str(passage["id"]),
                        "source": passage.get("source"),
                        "source_url": passage.get("source_url"),
                        "page": passage.get("page"),
                        "rerank_score": float(passage["score"]),
                        "text": passage["text"],
                    }
                    for rank, passage in enumerate(
                        passages, start=1
                    )
                ],
            }
        except Exception as error:
            result = {
                "case_id": case["id"],
                "question": case["question"],
                "status": "error",
                "latency_seconds": perf_counter() - started,
                "error_type": type(error).__name__,
            }

        results.append(result)
        print(
            f"  {result['status']} — "
            f"{result['latency_seconds']:.3f}s",
            flush=True,
        )

    output_dir = ROOT / "evaluation" / "runs"
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    output_path = output_dir / f"retrieval_{run_id}.json"

    report = {
        "run_id": run_id,
        "pipeline": "hybrid_rrf_flashrank",
        "initial_k": 15,
        "final_k": 5,
        "split": args.split,
        "latency_scope": (
            "Query embedding, Qdrant retrieval, and reranking; "
            "excludes module initialization and answer generation"
        ),
        "results": results,
    }

    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()