import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from core.generator import GENERATION_MODEL, generate_grounded_answer


ROOT = Path(__file__).resolve().parents[1]

WORKSHOP = (
    "Please note that your attendance at this workshop "
    "is not required in order to apply for CPT."
)

REMOTE = (
    "Any student working remotely on CPT must have this "
    "confirmed in the offer letter or in supporting documentation, "
    "the address where you will work remotely must also be "
    "mentioned by the employer."
)


def passage(text):
    return {
        "source_title": "Curricular Practical Training (CPT)",
        "publisher": "University of Maryland — ISSS",
        "page": None,
        "text": text,
    }


def build_cases():
    remote_question = (
        "What address documentation does UMD require "
        "for remote work on CPT?"
    )

    cases = [
        {
            "id": "remote_sufficient",
            "question": remote_question,
            "passages": [passage(REMOTE)],
            "expected_status": "citation_ids_valid",
        },
        {
            "id": "remote_insufficient",
            "question": remote_question,
            "passages": [passage(WORKSHOP)],
            "expected_status": "insufficient_evidence",
        },
        {
            "id": "ambiguous_question",
            "question": "Do I need it?",
            "passages": [passage(WORKSHOP)],
            "expected_status": "needs_clarification",
        },
        {
            "id": "explicit_question",
            "question": "Is workshop attendance required to apply for CPT?",
            "passages": [passage(WORKSHOP)],
            "expected_status": "citation_ids_valid",
        },
    ]

    # Use the preserved source, not a reconstructed interpretation of its wording.
    snapshot = "20261114T213307398026Z"
    source_text = (
        ROOT / "data/sources/umd_cpt" / snapshot / "content.txt"
    ).read_text(encoding="utf-8")
    start = source_text.index("Obtain an internship/co-op offer letter from an employer")
    end = source_text.index("Click here to see an example of an internship/co-op offer letter.", start)
    offer_letter = passage(source_text[start:end].strip())
    offer_letter["source_snapshot"] = snapshot

    cases.extend([
        {
            "id": "offer_letter_preserve_ambiguity",
            "question": "What must the UMD CPT employer offer letter include?",
            "passages": [offer_letter],
            "expected_status": "citation_ids_valid",
            "manual_review_criteria": [
                "Includes the supported checklist items and their conditions.",
                "Preserves the date footnote: dates within the semester of the CPT-associated course; employer email with a new later start date if the original date has passed or will pass by ISSS review.",
                "Quotes 'The specific term internship or co-op' and flags its meaning as unclear.",
                "Does not assert an academic-semester requirement or a literal-wording requirement from that phrase.",
            ],
        },
        {
            "id": "offer_letter_term_interpretation",
            "question": (
                "In UMD's CPT offer-letter checklist, does 'The specific term "
                "internship or co-op' mean the academic semester, or must the "
                "letter literally say internship or co-op?"
            ),
            "passages": [offer_letter],
            "expected_status": "insufficient_evidence",
            "manual_review_criteria": [
                "Does not choose either interpretation of the ambiguous source phrase.",
                "Treats the source evidence as insufficient, rather than asking the user to clarify an already clear question.",
            ],
        },
        {
            "id": "offer_letter_explicit_dates",
            "question": "Does the UMD CPT offer letter need specific internship start and end dates?",
            "passages": [offer_letter],
            "expected_status": "citation_ids_valid",
            "manual_review_criteria": [
                "Answers yes using the explicit start/end-date checklist item, with a citation.",
                "Does not turn the unrelated ambiguous term item into an extra requirement.",
            ],
        },
        {
            "id": "offer_letter_date_footnote_conditions",
            "question": (
                "What semester restriction applies to UMD CPT internship dates, "
                "and what does UMD ask for if the internship start date has "
                "already passed or will pass by the time ISSS reviews the application?"
            ),
            "passages": [offer_letter],
            "expected_status": "citation_ids_valid",
            "manual_review_criteria": [
                "Dates must be within the semester the student is registered for the course associated with CPT, with a citation.",
                "Preserves both triggers: the start date has passed OR will pass by ISSS review.",
                "Requests an email from the employer indicating a new later start date, with a citation.",
                "Does not claim the later date permits work before authorization or guarantees approval.",
                "Does not use the date footnote to resolve the separate ambiguous 'specific term' phrase.",
            ],
        },
    ])
    return cases


def main():
    parser = argparse.ArgumentParser(description="Evaluate generation with supplied development evidence.")
    parser.add_argument("--case", action="append", dest="case_ids",
                        help="Run only this case ID; repeat to select multiple cases.")
    args = parser.parse_args()
    cases = build_cases()
    if args.case_ids:
        unknown = set(args.case_ids) - {case["id"] for case in cases}
        if unknown:
            parser.error(f"Unknown case IDs: {', '.join(sorted(unknown))}")
        cases = [case for case in cases if case["id"] in args.case_ids]

    # Capture which generator implementation produced this run.
    generator_hash = hashlib.sha256(
        (ROOT / "core/generator.py").read_bytes()
    ).hexdigest()

    results = []

    for case in cases:
        print(f"Running: {case['id']}", flush=True)
        started = perf_counter()

        try:
            result = generate_grounded_answer(
                question=case["question"],
                passages=case["passages"],
            )
            row = {
                **case,
                "execution_status": "ok",
                "actual_status": result["status"],
                "answer": result["answer"],
                "citation_errors": result["citation_errors"],
                "outcome_match": (
                    result["status"] == case["expected_status"]
                ),
                "manual_review_status": "pending",
            }
        except Exception as error:
            # Never serialize exception messages or response bodies: they can
            # contain request details. A numeric API code is enough for triage.
            error_code = getattr(error, "code", None)
            row = {
                **case,
                "execution_status": "error",
                "error_type": type(error).__name__,
                "error_code": error_code if type(error_code) is int else None,
                "outcome_match": False,
            }

        row["latency_seconds"] = perf_counter() - started
        results.append(row)

        print(
            f"  Outcome match: {row['outcome_match']} | "
            f"{row['latency_seconds']:.3f}s",
            flush=True,
        )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = ROOT / "evaluation/runs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"generation_{run_id}.json"

    matches = sum(row["outcome_match"] for row in results)
    execution_errors = sum(row["execution_status"] == "error" for row in results)

    report = {
        "run_id": run_id,
        "model": GENERATION_MODEL,
        "generator_sha256": generator_hash,
        "evaluator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scope": f"{len(cases)} development examples with supplied evidence; no retrieval",
        "manual_review_note": (
            "Outcome matching checks status only. Review answers against supplied "
            "evidence and case criteria; citation IDs do not establish claim support."
        ),
        "latency_scope": (
            "Generation and response validation; excludes module initialization"
        ),
        "historical_note": (
            "The ambiguous question initially produced an answer by inferring "
            "the pronoun referent from the excerpt. A prompt revision requested "
            "clarification instead; the subsequent manual check passed."
        ),
        "outcome_matches": matches,
        "execution_errors": execution_errors,
        "completed_outcome_mismatches": sum(
            row["execution_status"] == "ok" and not row["outcome_match"]
            for row in results
        ),
        "case_count": len(cases),
        "results": results,
    }

    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"\nOutcome matches: {matches}/{len(cases)}")
    print(f"Execution errors: {execution_errors}")
    print(f"Saved: {output}")
    print("Outcome matching does not establish factual correctness.")


if __name__ == "__main__":
    main()
