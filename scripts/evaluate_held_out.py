import json
from datetime import datetime, timezone
from pathlib import Path

from core.retriever import retrieve_candidates, rerank_candidates


ROOT = Path(__file__).resolve().parents[1]


def fuse_rankings(hybrid, reranked):
    hybrid_ranks = {
        point_id: rank
        for rank, point_id in enumerate(hybrid, start=1)
    }
    reranked_ranks = {
        point_id: rank
        for rank, point_id in enumerate(reranked, start=1)
    }

    assert len(set(hybrid)) == len(hybrid)
    assert len(set(reranked)) == len(reranked)
    assert set(hybrid) == set(reranked)

    return sorted(
        hybrid,
        key=lambda point_id: (
            -(
                1 / (60 + hybrid_ranks[point_id])
                + 1 / (60 + reranked_ranks[point_id])
            ),
            hybrid_ranks[point_id],
        ),
    )


def main():
    cases = json.loads(
        (ROOT / "evaluation/cases.json").read_text(encoding="utf-8")
    )
    cases = [c for c in cases if c["split"] == "held_out"]

    evidence = json.loads(
        (ROOT / "evaluation/held_out_evidence.json").read_text(
            encoding="utf-8"
        )
    )

    if not cases:
        raise ValueError("No held-out cases found.")

    # Validate all labels before making API calls.
    for case in cases:
        if case["source_snapshot"] != evidence["source_snapshot"]:
            raise ValueError(f"Snapshot mismatch: {case['id']}")

        groups = evidence["cases"][case["id"]]["evidence_groups"]
        if not groups or any(not g["point_ids"] for g in groups):
            raise ValueError(f"Incomplete labels: {case['id']}")

    results = []
    totals = {}

    for case in cases:
        print(f"\n{case['id']}", flush=True)

        passages = {
            mode: retrieve_candidates(
                case["question"], mode=mode, initial_k=15
            )
            for mode in ("dense", "sparse", "hybrid")
        }
        passages["hybrid_reranked"] = rerank_candidates(
            case["question"], passages["hybrid"]
        )

        rankings = {
            name: [str(p["id"]) for p in points]
            for name, points in passages.items()
        }
        rankings["hybrid_reranked_rrf60"] = fuse_rankings(
            rankings["hybrid"],
            rankings["hybrid_reranked"],
        )

        groups = evidence["cases"][case["id"]]["evidence_groups"]
        row = {
            "case_id": case["id"],
            "question": case["question"],
            "rankings": rankings,
            "coverage": {},
        }

        for name, point_ids in rankings.items():
            totals.setdefault(
                name,
                {
                    k: {"any": 0, "complete": 0}
                    for k in (1, 4, 5)
                },
            )
            row["coverage"][name] = {}

            for k in (1, 4, 5):
                retrieved = set(point_ids[:k])
                covered = [
                    bool(retrieved.intersection(group["point_ids"]))
                    for group in groups
                ]

                any_hit = any(covered)
                complete = all(covered)

                totals[name][k]["any"] += int(any_hit)
                totals[name][k]["complete"] += int(complete)

                row["coverage"][name][k] = {
                    "groups_covered": sum(covered),
                    "groups_total": len(groups),
                    "any_evidence": any_hit,
                    "complete_evidence": complete,
                }

            coverage = row["coverage"][name][5]
            print(
                f"  {name}: top-5 evidence groups "
                f"{coverage['groups_covered']}/"
                f"{coverage['groups_total']}"
            )

        results.append(row)

    count = len(cases)

    for name, cutoffs in totals.items():
        print(f"\n{name}")
        for k, counts in cutoffs.items():
            print(
                f"  @{k}: any evidence {counts['any']}/{count}; "
                f"complete evidence {counts['complete']}/{count}"
            )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = ROOT / "evaluation/runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"held_out_{run_id}.json"

    output.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "split": "held_out",
                "initial_k": 15,
                "rrf_constant": 60,
                "rrf_tie_break": "hybrid_rank",
                "evidence_labels": evidence,
                "case_count": count,
                "totals": totals,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved: {output}")


if __name__ == "__main__":
    main()