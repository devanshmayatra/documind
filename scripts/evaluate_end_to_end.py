"""Development checks through the app's first-turn retrieval/generation path."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from scripts.eval_pacing import paced_cases
from time import perf_counter

from core.generator import GENERATION_MODEL, generate_grounded_answer, rewrite_query
from core.qdrant_engine import COLLECTION_NAME
from core.retriever import hybrid_search_and_rerank
from scripts.evaluate_generation import build_cases


ROOT = Path(__file__).resolve().parents[1]


def run_case(case):
    # Reference passages are deliberately excluded from generation inputs.
    row = {
        "case_id": case["id"],
        "question": case["question"],
        "reference_expected_status": case["expected_status"],
        "reference_source_snapshot": (case.get("source_snapshot") or case["passages"][0]["source_snapshot"]),
        "manual_review_criteria": case["manual_review_criteria"],
        "manual_review_status": "pending",
        "passages": [],
    }
    started = perf_counter()
    stage = "rewrite"
    try:
        query = rewrite_query(case["question"], [])
        row["rewritten_query"] = query
        stage = "retrieval"
        passages = hybrid_search_and_rerank(query, initial_k=15, final_k=4)
        for rank, passage in enumerate(passages, start=1):
            saved = {key: passage.get(key) for key in (
                "text", "source", "page", "source_url", "publisher",
                "source_title", "retrieved_at", "source_updated_at", "source_id", "source_content_sha256",
            )}
            saved.update({
                "rank": rank,
                "citation_id": f"[S{rank}]",
                "point_id": str(passage["id"]),
                "rerank_score": float(passage["score"]) if passage.get("score") is not None else None,
            })
            row["passages"].append(saved)
        if "expected_source_id" in case:
            row["expected_source_id"] = case["expected_source_id"]
            row["expected_source_retrieved"] = any(
                p["source_id"] == case["expected_source_id"] for p in row["passages"]
            )
        row["retrieval_and_rewrite_seconds"] = perf_counter() - started
        stage = "generation"
        result = generate_grounded_answer(question=query, passages=passages)
        row.update({
            "execution_status": "ok",
            "actual_status": result["status"],
            "answer": result["answer"],
            "citation_errors": result["citation_errors"],
            "reference_outcome_match": result["status"] == case["expected_status"],
        })
    except Exception as error:
        code = getattr(error, "code", None)
        # Save class names only; wrapped transport messages may contain URLs.
        cause = error.__cause__ or error.__context__
        row.update({
            "execution_status": "error",
            "error_stage": stage,
            "error_type": type(error).__name__,
            "error_cause_type": type(cause).__name__ if cause is not None else None,
            "error_code": code if type(code) is int else None,
            "reference_outcome_match": None,
        })
    row["latency_seconds"] = perf_counter() - started
    return row


def main():
    cases = [case for case in build_cases() if case["id"].startswith("offer_letter_")]
    cases.extend(json.loads((ROOT / "evaluation/employment_cases.json").read_text(encoding="utf-8")))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", dest="case_ids",
                        choices=[case["id"] for case in cases],
                        help="Run only this development case; repeat to select multiple.")
    args = parser.parse_args()
    if args.case_ids:
        cases = [case for case in cases if case["id"] in args.case_ids]
    results = []
    for case in paced_cases(cases):
        print(f"Running: {case['id']}", flush=True)
        row = run_case(case)
        results.append(row)
        print(f"  Execution: {row['execution_status']} | "
              f"Reference outcome match: {row['reference_outcome_match']} | "
              f"{row['latency_seconds']:.3f}s", flush=True)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = {
        "run_id": run_id,
        "scope": "UMD employment development cases; live retrieval and generation, empty chat history; no Streamlit UI",
        "pipeline": "hybrid_rrf_flashrank",
        "initial_k": 15,
        "final_k": 4,
        "collection": COLLECTION_NAME,
        "model": GENERATION_MODEL,
        "implementation_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("core/retriever.py", "core/generator.py", "core/qdrant_engine.py",
                         "scripts/evaluate_generation.py", "scripts/evaluate_end_to_end.py")
        },
        "review_note": (
            "Expected statuses come from supplied-evidence development cases. "
            "Review actual retrieved evidence before treating a mismatch as a generation error. "
            "A matching status or valid citation IDs do not establish factual support. "
            "Reference snapshot is a label, not verification of the live corpus version."
        ),
        "latency_scope": "Rewrite, embedding, retrieval, reranking, generation and validation; excludes module initialization",
        "case_count": len(cases),
        "reference_outcome_matches": sum(row["reference_outcome_match"] is True for row in results),
        "execution_errors": sum(row["execution_status"] == "error" for row in results),
        "completed_reference_outcome_mismatches": sum(row["reference_outcome_match"] is False for row in results),
        "results": results,
    }
    output = ROOT / "evaluation/runs" / f"end_to_end_{run_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReference outcome matches: {report['reference_outcome_matches']}/{len(cases)}")
    print(f"Execution errors: {report['execution_errors']}")
    print(f"Saved: {output}")
    print("Inspect retrieved evidence and answer claims; outcome matching is not factual correctness.")


if __name__ == "__main__":
    main()
