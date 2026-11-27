"""Real SQLite and service orchestration; model/network calls are mocked."""
import ast
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch

from core.answer_cache import AnswerCache, is_general_question, source_manifest


ROOT = Path(__file__).resolve().parents[1]


class CacheTestBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = AnswerCache(Path(self.temp.name) / "answers.sqlite3")
        self.question = "What must the UMD CPT employer offer letter include?"
        self.token = self.cache.token()
        self.payload = {"query": self.question, "result": {"answer": "Claim [S1]"}}


class AnswerCacheTests(CacheTestBase):
    def test_persists_across_instances_and_normalizes_only_case_and_whitespace(self):
        self.cache.put(self.question, self.token, self.payload)
        other = AnswerCache(self.cache.path)
        self.assertEqual(other.get("  WHAT must the UMD CPT employer offer letter include?  ", other.token()), self.payload)
        self.assertIsNone(other.get(self.question.replace("include?", "not include?"), other.token()))
        self.assertNotEqual(self.cache.key("inside the US", self.token), self.cache.key("outside the US", self.token))
        self.assertNotEqual(self.cache.key("20 hours", self.token), self.cache.key("40 hours", self.token))

    def test_expiry_is_a_miss(self):
        self.cache.ttl = -1
        self.cache.put(self.question, self.token, self.payload)
        self.assertIsNone(self.cache.get(self.question, self.token))

    def test_ingestion_invalidates_and_blocks_inflight_old_writes_even_on_failure(self):
        self.cache.put(self.question, self.token, self.payload)
        with self.assertRaises(RuntimeError):
            with self.cache.corpus_update():
                self.assertIsNone(self.cache.token())
                self.assertIsNone(self.cache.get(self.question, self.token))
                raise RuntimeError("upload failed")
        self.assertNotEqual(self.cache.token(), self.token)
        self.cache.put(self.question, self.token, self.payload)
        self.assertIsNone(self.cache.get(self.question, self.cache.token()))

    def test_pipeline_change_invalidates(self):
        self.cache.put(self.question, self.token, self.payload)
        with patch("core.answer_cache.pipeline_fingerprint", return_value="new-version"):
            self.assertIsNone(self.cache.get(self.question, self.cache.token()))

    def test_actual_upload_wrapper_invalidates_on_partial_failure(self):
        tree = ast.parse((ROOT / "core/qdrant_engine.py").read_text(encoding="utf-8"))
        wrapper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upload_chunks")
        upload = Mock(side_effect=RuntimeError("partial upload"))
        scope = {"_upload_chunks": upload}
        exec(compile(ast.Module(body=[wrapper], type_ignores=[]), "<upload wrapper>", "exec"), scope)
        self.cache.put(self.question, self.token, self.payload)
        with patch("core.answer_cache.AnswerCache", return_value=self.cache):
            with self.assertRaises(RuntimeError):
                scope["upload_chunks"]([{"text": "new source"}], batch_size=3)
        upload.assert_called_once_with([{"text": "new source"}], 3)
        self.assertIsNone(self.cache.get(self.question, self.cache.token()))

    def test_personal_questions_and_history_are_ineligible(self):
        for question in ("Can I apply for CPT?", "What is my CPT status?",
                         "What about CPT for me at a@b.com?", "What about student id 1234567?"):
            self.assertFalse(is_general_question(question, []))
        self.assertFalse(is_general_question(self.question, [{"role": "user", "content": "prior question"}]))


class AnswerServiceTests(CacheTestBase):
    def setUp(self):
        super().setUp()
        metadata = source_manifest()["umd_cpt"]
        self.passages = [{"id": "official-chunk", "text": "Evidence", "source_id": "umd_cpt",
                          "source_url": metadata["source_url"], "retrieved_at": metadata["retrieved_at"],
                          "source_updated_at": None, "source_content_sha256": metadata["content_sha256"]}]
        self.rewrite = Mock(side_effect=lambda question, history: question)
        self.retrieve = Mock(return_value=self.passages)
        self.generate = Mock(return_value={"answer": "Claim [S1]", "status": "citation_ids_valid", "citation_errors": []})
        generator = ast.parse((ROOT / "core/generator.py").read_text(encoding="utf-8"))
        validator = next(n for n in generator.body if isinstance(n, ast.FunctionDef) and n.name == "validate_citation_ids")
        scope = {"re": re, "rewrite_query": self.rewrite, "hybrid_search_and_rerank": self.retrieve,
                 "generate_grounded_answer": self.generate}
        exec(compile(ast.Module(body=[validator], type_ignores=[]), "<validator>", "exec"), scope)
        tree = ast.parse((ROOT / "core/answer_service.py").read_text(encoding="utf-8"))
        tree.body = [n for n in tree.body if not (isinstance(n, ast.ImportFrom)
                     and n.module in {"core.generator", "core.retriever"})]
        exec(compile(tree, str(ROOT / "core/answer_service.py"), "exec"), scope)
        self.answer = scope["answer_question"]

    def test_only_explicitly_shared_general_questions_appear_in_public_list(self):
        self.answer(self.question, [], self.cache)
        self.assertEqual(self.cache.recent_questions(), [])
        self.assertTrue(self.answer(self.question, [], self.cache, share_publicly=True)["cache_hit"])
        self.answer(self.question.upper(), [], self.cache, share_publicly=True)
        self.answer("What is my status?", [], self.cache, share_publicly=True)
        self.answer("What about remote work?", ["previous turn"], self.cache, share_publicly=True)
        self.answer("What are the dates?", [], self.cache, allow_shared_cache=False, share_publicly=True)
        self.assertEqual(self.cache.recent_questions(), [self.question])
        other = "What does UMD require for remote work?"
        self.answer(other, [], self.cache, share_publicly=True)
        self.assertEqual(AnswerCache(self.cache.path).recent_questions(), [other, self.question])

    def test_second_visitor_reuses_answer_without_any_pipeline_calls(self):
        first = self.answer(self.question, [], self.cache)
        self.assertFalse(first["cache_hit"])
        second = self.answer(self.question.upper(), [], AnswerCache(self.cache.path))
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["passages"], first["passages"])
        self.assertEqual(second["result"], first["result"])
        self.rewrite.assert_called_once()
        self.retrieve.assert_called_once()
        self.generate.assert_called_once()

    def test_followup_always_runs_pipeline(self):
        self.answer(self.question, [], self.cache)
        response = self.answer(self.question, [{"role": "user", "content": "context"}], self.cache)
        self.assertFalse(response["cache_hit"])
        self.assertEqual(self.retrieve.call_count, 2)

    def test_user_can_bypass_shared_storage_and_lookup(self):
        cache = Mock()
        response = self.answer(self.question, [], cache, allow_shared_cache=False)
        self.assertFalse(response["cache_hit"])
        cache.token.assert_not_called()
        cache.get.assert_not_called()
        cache.put.assert_not_called()

    def test_abstention_is_not_cached(self):
        self.generate.return_value = {"answer": "Insufficient", "status": "insufficient_evidence", "citation_errors": []}
        for _ in range(2):
            self.assertFalse(self.answer(self.question, [], self.cache)["cache_hit"])
        self.assertEqual(self.generate.call_count, 2)

    def test_api_failure_is_not_cached(self):
        self.generate.side_effect = RuntimeError("API failure")
        with self.assertRaises(RuntimeError):
            self.answer(self.question, [], self.cache)
        self.assertIsNone(self.cache.get(self.question, self.cache.token()))

    def test_unregistered_upload_is_not_cached(self):
        self.passages[0].pop("source_id")
        for _ in range(2):
            self.assertFalse(self.answer(self.question, [], self.cache)["cache_hit"])
        self.assertEqual(self.generate.call_count, 2)

    def test_old_source_version_is_not_cached(self):
        self.passages[0]["source_content_sha256"] = "retired-hash"
        self.answer(self.question, [], self.cache)
        self.assertIsNone(self.cache.get(self.question, self.cache.token()))

    def test_storage_failure_falls_back_to_pipeline(self):
        cache = Mock()
        cache.token.side_effect = OSError("unavailable")
        self.assertFalse(self.answer(self.question, [], cache)["cache_hit"])
        self.generate.assert_called_once()

    def test_invalid_citation_in_saved_answer_is_not_reused(self):
        self.cache.put(self.question, self.cache.token(), {
            "query": self.question, "passages": self.passages,
            "result": {"answer": "Unsupported [S99]", "status": "citation_ids_valid", "citation_errors": []},
        })
        self.assertFalse(self.answer(self.question, [], self.cache)["cache_hit"])
        self.generate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
