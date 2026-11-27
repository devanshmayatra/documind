import json
from datetime import datetime, timezone
from pathlib import Path
from scripts.eval_pacing import paced_cases

from core.retriever import retrieve_candidates, rerank_candidates


ROOT = Path(__file__).resolve().parents[1]


def main():
    cases = json.loads(
        (ROOT / "evaluation/cases.json").read_text(encoding="utf-8")
    )
    labels = json.loads(
        (ROOT / "evaluation/supporting_points.json").read_text(
            encoding="utf-8"
        )
    )["cases"]

    cases = [case for case in cases if case["split"] == "development"]
    if not cases:
        raise ValueError("No development cases found.")

    missing = [case["id"] for case in cases if not labels.get(case["id"])]
    if missing:
        raise ValueError(f"Missing labels: {missing}")

    results = []
    totals = {
        name: {1: 0, 5: 0}
        for name in (
            "dense",
            "sparse",
            "hybrid",
            "hybrid_reranked",
        )
    }

    for case in paced_cases(cases):
        print(f"\n{case['id']}", flush=True)
        expected = set(labels[case["id"]])

        rankings = {
            mode: retrieve_candidates(
                case["question"],
                mode=mode,
                initial_k=15,
            )
            for mode in ("dense", "sparse", "hybrid")
        }

        rankings["hybrid_reranked"] = rerank_candidates(
            case["question"],
            rankings["hybrid"],
        )

        row = {
            "case_id": case["id"],
            "question": case["question"],
        }

        for name, points in rankings.items():
            first_match = next(
                (
                    rank
                    for rank, passage in enumerate(points, start=1)
                    if str(passage["id"]) in expected
                ),
                None,
            )

            row[name] = {
                "supporting_rank": first_match,
                "point_ids": [str(p["id"]) for p in points],
            }

            for k in (1, 5):
                totals[name][k] += int(
                    first_match is not None and first_match <= k
                )

            print(f"  {name}: supporting rank = {first_match}")

        results.append(row)

    metrics = {}
    for name, counts in totals.items():
        metrics[name] = {
            f"hit_at_{k}": {
                "hits": hits,
                "cases": len(cases),
                "rate": hits / len(cases),
            }
            for k, hits in counts.items()
        }

        print(f"\n{name}")
        for k, hits in counts.items():
            print(
                f"  Hit@{k}: {hits}/{len(cases)} "
                f"({hits / len(cases):.1%})"
            )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = ROOT / "evaluation/runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"ranking_comparison_{run_id}.json"

    output_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "split": "development",
                "initial_k": 15,
                "label_scope": (
                    "Selected supporting-point IDs; "
                    "not exhaustive relevance judgments"
                ),
                "metrics": metrics,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
