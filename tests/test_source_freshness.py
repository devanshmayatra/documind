"""Exercise actual retrieval/rendering functions without live services."""
import ast
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]


def load_functions(path, names, scope):
    # Avoid the modules' import-time clients, models, and Streamlit app startup.
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in nodes} == set(names)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / path), "exec"), scope)


class SourceFreshnessTests(unittest.TestCase):
    def retrieve_and_render(self, metadata):
        payload = {"text": "CPT source passage", "source": "umd_cpt.txt", **metadata}
        client = Mock()
        client.query_points.return_value = SimpleNamespace(
            points=[SimpleNamespace(id="cpt-chunk", payload=payload)])
        scope = {"qdrant": client, "COLLECTION_NAME": "offline",
                 "get_dense_vector": Mock(return_value=[0.0])}
        load_functions("core/retriever.py", ["retrieve_candidates"], scope)
        passages = scope["retrieve_candidates"]("CPT", mode="dense")
        self.assertEqual(passages[0]["retrieved_at"], metadata.get("retrieved_at"))
        self.assertEqual(passages[0]["source_updated_at"], metadata.get("source_updated_at"))
        ui = Mock()
        ui.expander.return_value = nullcontext()
        ui.container.return_value = nullcontext()
        scope = {"st": ui, "datetime": datetime, "urlsplit": urlsplit}
        load_functions("app.py", ["format_page_label", "format_source_date", "render_sources"], scope)
        scope["render_sources"](passages)
        return [call.args[0] for call in ui.caption.call_args_list]

    def test_cpt_timestamp_and_unknown_policy_date(self):
        captions = self.retrieve_and_render({
            "retrieved_at": "2026-11-14T21:33:07.398026+00:00",
            "source_updated_at": None,
        })
        self.assertIn("Retrieved on: 2026-11-14", captions)
        self.assertIn("Source updated: Unknown", captions)

    def test_both_fields_absent(self):
        captions = self.retrieve_and_render({})
        self.assertIn("Retrieved on: Unknown", captions)
        self.assertIn("Source updated: Unknown", captions)

    def test_dates_remain_independent(self):
        captions = self.retrieve_and_render({
            "retrieved_at": "2026-11-14T21:33:07.398026+00:00",
            "source_updated_at": "2026-10-01",
        })
        self.assertIn("Retrieved on: 2026-11-14", captions)
        self.assertIn("Source updated: 2026-10-01", captions)


if __name__ == "__main__":
    unittest.main()
