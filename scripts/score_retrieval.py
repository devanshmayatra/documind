import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_file", type=Path)
    args = parser.parse_args()

    report = json.loads(
        args.run_file.read_text(encoding="utf-8")
    )
    labels = json.loads(
        (ROOT / "evaluation" / "supporting_points.json").read_text(
            encoding="utf-8"
        )
    )["cases"]

    results = report["results"]
    case_ids = [result["case_id"] for result in results]

    if not results:
        raise ValueError("The run contains no results.")

    if len(case_ids) != len(set(case_ids)):
        raise ValueError("The run contains duplicate case IDs.")

    missing = [case_id for case_id in case_ids if not labels.get(case_id)]
    if missing:
        raise ValueError(f"Missing supporting-point labels: {missing}")

    totals = {1: 0, 5: 0}

    for result in results:
        expected = set(labels[result["case_id"]])

        # Execution failures count as misses, not silently excluded cases.
        passages = (
            sorted(result["passages"], key=lambda p: p["rank"])
            if result["status"] == "ok"
            else []
        )

        first_match = next(
            (
                passage["rank"]
                for passage in passages
                if passage["point_id"] in expected
            ),
            None,
        )

        print(
            f"{result['case_id']}: "
            f"supporting rank = {first_match}; "
            f"status = {result['status']}"
        )

        for k in totals:
            totals[k] += int(
                first_match is not None and first_match <= k
            )

    count = len(results)

    print(f"\nScored cases: {count}")
    for k, hits in totals.items():
        print(
            f"Supporting-passage Hit@{k}: "
            f"{hits}/{count} ({hits / count:.1%})"
        )

    print(
        "\nScope: selected supporting-point IDs in this saved run; "
        "not exhaustive passage recall or answer accuracy."
    )


if __name__ == "__main__":
    main()