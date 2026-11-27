"""Replay saved split-passage evidence offline; no claim of model correctness."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


class ChecklistPromptTests(unittest.TestCase):
    def test_saved_split_evidence_reaches_actual_generation_prompt(self):
        report = json.loads((ROOT / self.report_path)
                            .read_text(encoding="utf-8"))
        case = next(row for row in report["results"]
                    if row["case_id"] == "offer_letter_preserve_ambiguity")
        passages = case["passages"]
        self.assertIn("*Internship dates must", passages[0]["text"])
        self.assertIn("Official company letterhead", passages[2]["text"])

        # Return the recorded incomplete answer, not a fabricated successful
        # model answer. This also exposes the ID validator's remaining limit.
        client = Mock()
        client.models.generate_content_stream.return_value = [SimpleNamespace(
            text=json.dumps({"outcome": "answered", "answer": case["answer"]}))]
        source = ROOT / "core/generator.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        tree.body = [node for node in tree.body
                     if not (isinstance(node, ast.ImportFrom)
                             and node.module == "core.qdrant_engine")]
        scope = {"ai_client": client}
        exec(compile(tree, str(source), "exec"), scope)
        result = scope["generate_grounded_answer"](case["question"], passages)
        client.models.generate_content_stream.assert_called_once()
        sent = client.models.generate_content_stream.call_args.kwargs["contents"]
        context = sent.split("Source excerpts:\n", 1)[1].rsplit("\n\nQuestion:", 1)[0]
        for index, passage in enumerate(passages, start=1):
            self.assertIn(f"[S{index}] {passage['source_title']}", context)
            self.assertIn(f"Excerpt:\n{passage['text']}", context)
        self.assertIn("different passage from the checklist", sent)
        self.assertIn("do not expand into separate course registration exceptions", sent)
        self.assertIn("Never present only some prerequisites as sufficient", sent)
        self.assertIn("has passed or will pass by the time ISSS reviews", context)
        self.assertIn("email from your employer indicating a new later start date", context)
        self.assertEqual(result["answer"], case["answer"])
        self.assertEqual(result["status"], "citation_ids_valid")
        self.assertEqual(result["citation_errors"], [])

    report_path = "evaluation/runs/end_to_end_20261115T142328883386Z.json"


class ChecklistExpansionPromptTests(ChecklistPromptTests):
    # Same evidence-delivery check against the later answer that included an
    # incomplete winter exception. Mocked answers are not semantic successes.
    report_path = "evaluation/runs/end_to_end_20261126T180118110525Z.json"


if __name__ == "__main__":
    unittest.main()
