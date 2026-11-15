from unittest.mock import patch

from core.generator import (
    NO_EVIDENCE_MESSAGE,
    generate_grounded_answer,
    validate_citation_ids,
)


def main():
    cases = [
        ("Valid citation", "A claim [S1].", 4, []),
        ("Multiple citations", "A claim [S1][S3].", 4, []),
        (
            "Unknown citation",
            "A claim [S999].",
            4,
            ["invalid_citations: [S999]"],
        ),
        (
            "Malformed citation",
            "A claim [S1, S2].",
            4,
            ["invalid_citations: [S1, S2]"],
        ),
        (
            "Missing citation",
            "A claim without a citation.",
            4,
            ["missing_citations"],
        ),
        (
            "Empty answer",
            "",
            4,
            ["empty_answer", "missing_citations"],
        ),
    ]

    for name, answer, passage_count, expected in cases:
        actual = validate_citation_ids(answer, passage_count)
        assert actual == expected, (
            f"{name}: expected {expected}, got {actual}"
        )
        print(f"PASS: {name}")

    # Fail immediately if empty retrieval attempts a generation call.
    with patch(
        "core.generator.ai_client.models.generate_content_stream",
        side_effect=AssertionError(
            "Empty retrieval must not call the generation API."
        ),
    ) as generation_mock:
        result = generate_grounded_answer(
            question="What documents do I need?",
            passages=[],
        )

        generation_mock.assert_not_called()

    assert result == {
        "answer": NO_EVIDENCE_MESSAGE,
        "status": "no_evidence",
        "citation_errors": [],
    }
    print("PASS: Empty retrieval returns fallback without generation")

    print("\nAll 7 checks passed.")


if __name__ == "__main__":
    main()