"""Offline orchestration checks; do not initialize models or clients."""
import ast
from pathlib import Path
from time import perf_counter
import unittest
from unittest.mock import Mock


class EndToEndEvaluationTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / "scripts/evaluate_end_to_end.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_case")
        self.rewrite = Mock(return_value="rewritten question")
        self.passages = [{"id": "live-id", "text": "live evidence", "score": 0.5,
                          "retrieved_at": "2026-11-14", "source_updated_at": None}]
        self.retrieve = Mock(return_value=self.passages)
        self.generate = Mock(return_value={"status": "citation_ids_valid",
                                           "answer": "Supported [S1]", "citation_errors": []})
        scope = {"perf_counter": perf_counter, "rewrite_query": self.rewrite,
                 "hybrid_search_and_rerank": self.retrieve,
                 "generate_grounded_answer": self.generate}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), scope)
        self.run_case = scope["run_case"]
        self.case = {"id": "offer_letter_test", "question": "question",
                     "passages": [{"source_snapshot": "reference", "text": "fixture must not leak"}],
                     "expected_status": "citation_ids_valid", "manual_review_criteria": ["review"]}

    def test_uses_production_settings_and_only_live_evidence(self):
        row = self.run_case(self.case)
        self.rewrite.assert_called_once_with("question", [])
        self.retrieve.assert_called_once_with("rewritten question", initial_k=15, final_k=4)
        self.generate.assert_called_once_with(question="rewritten question", passages=self.passages)
        self.assertTrue(row["reference_outcome_match"])
        self.assertEqual(row["passages"][0]["citation_id"], "[S1]")
        self.assertEqual(row["passages"][0]["point_id"], "live-id")
        self.assertIsNone(row["passages"][0]["source_updated_at"])
        self.assertNotIn("fixture must not leak", str(row))

    def test_retrieval_error_does_not_call_generation(self):
        self.retrieve.side_effect = RuntimeError("private response body")
        row = self.run_case(self.case)
        self.generate.assert_not_called()
        self.assertEqual(row["error_stage"], "retrieval")
        self.assertIsNone(row["reference_outcome_match"])
        self.assertNotIn("private response body", str(row))

    def test_wrapped_transport_error_records_only_cause_type(self):
        def wrapped_failure(*args, **kwargs):
            try:
                raise TimeoutError("private connection details")
            except TimeoutError as cause:
                raise RuntimeError("private wrapper details") from cause
        self.retrieve.side_effect = wrapped_failure
        row = self.run_case(self.case)
        self.assertEqual(row["error_type"], "RuntimeError")
        self.assertEqual(row["error_cause_type"], "TimeoutError")
        self.assertNotIn("private connection details", str(row))
        self.assertNotIn("private wrapper details", str(row))
        self.generate.assert_not_called()

    def test_generation_error_keeps_retrieved_evidence(self):
        class ClientError(Exception):
            code = 429
        self.generate.side_effect = ClientError("private request")
        row = self.run_case(self.case)
        self.assertEqual(row["error_stage"], "generation")
        self.assertEqual(row["error_code"], 429)
        self.assertEqual(row["passages"][0]["text"], "live evidence")
        self.assertNotIn("private request", str(row))

    def test_abstention_is_completed_mismatch_not_execution_error(self):
        self.retrieve.return_value = []
        self.generate.return_value = {"status": "no_evidence", "answer": "fallback", "citation_errors": []}
        row = self.run_case(self.case)
        self.assertEqual(row["execution_status"], "ok")
        self.assertFalse(row["reference_outcome_match"])
        self.generate.assert_called_once_with(question="rewritten question", passages=[])


if __name__ == "__main__":
    unittest.main()
