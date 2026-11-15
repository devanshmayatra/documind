"""Offline checks: python -B -m unittest discover -s tests -v.

Extract setup functions to avoid importing live clients and embedding models.
"""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock


class CollectionSetupTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.collection_exists.return_value = True
        self.info = NS(config=NS(params=NS(vectors={"dense": NS(size=3072)})), payload_schema={})
        self.client.get_collection.return_value = self.info
        models = NS(
            PayloadSchemaType=NS(KEYWORD="keyword"),
            VectorParams=lambda **kw: kw, SparseVectorParams=lambda **kw: kw,
            Distance=NS(COSINE="Cosine"), Modifier=NS(IDF="idf"),
        )
        source = Path(__file__).resolve().parents[1] / "core" / "qdrant_engine.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name in {"ensure_source_id_index", "setup_collection"}]
        scope = {"qdrant": self.client, "models": models,
                 "COLLECTION_NAME": "test_collection", "EMBEDDING_DIM": 3072}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), scope)
        self.setup_collection = scope["setup_collection"]

    def assert_index_created(self):
        self.client.create_payload_index.assert_called_once_with(
            collection_name="test_collection", field_name="source_id",
            field_schema="keyword", wait=True,
        )

    def test_existing_collection_gets_missing_index(self):
        self.setup_collection()
        self.assert_index_created()
        self.client.create_collection.assert_not_called()
        self.client.delete_collection.assert_not_called()
        self.client.delete_payload_index.assert_not_called()

    def test_existing_keyword_index_is_kept_on_repeated_setup(self):
        self.info.payload_schema["source_id"] = NS(data_type="keyword")
        self.setup_collection()
        self.setup_collection()
        self.client.create_payload_index.assert_not_called()
        self.client.create_collection.assert_not_called()

    def test_wrong_index_type_is_preserved_and_rejected(self):
        self.info.payload_schema["source_id"] = NS(data_type="integer")
        with self.assertRaisesRegex(ValueError, "non-keyword source_id"):
            self.setup_collection()
        self.client.create_payload_index.assert_not_called()
        self.client.delete_payload_index.assert_not_called()

    def test_new_collection_is_created_before_index(self):
        self.client.collection_exists.return_value = False
        self.setup_collection()
        self.client.create_collection.assert_called_once()
        self.assert_index_created()
        self.assertEqual([call[0] for call in self.client.method_calls],
                         ["collection_exists", "create_collection", "create_payload_index"])

    def test_incompatible_vectors_fail_before_index_changes(self):
        for vectors in ({}, {"dense": NS(size=768)}):
            with self.subTest(vectors=vectors):
                self.info.config.params.vectors = vectors
                with self.assertRaises(ValueError):
                    self.setup_collection()
        self.client.create_payload_index.assert_not_called()
        self.client.create_collection.assert_not_called()

    def test_index_creation_failure_is_not_hidden(self):
        self.client.create_payload_index.side_effect = RuntimeError("index unavailable")
        with self.assertRaisesRegex(RuntimeError, "index unavailable"):
            self.setup_collection()


if __name__ == "__main__":
    unittest.main()
