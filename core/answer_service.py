"""Use shared cached answers before invoking the existing RAG pipeline."""
import sqlite3
from core.answer_cache import AnswerCache, cache_failure, is_general_question, official_passages
from core.generator import generate_grounded_answer, rewrite_query, validate_citation_ids
from core.retriever import hybrid_search_and_rerank


def answer_question(question, history, cache=None, allow_shared_cache=True, share_publicly=False):
    cache = cache if cache is not None else AnswerCache()
    eligible = allow_shared_cache and is_general_question(question, history)
    token = None
    if eligible:
        try:
            token = cache.token()
            hit = cache.get(question, token)
            if (hit and official_passages(hit["passages"])
                    and hit["result"]["status"] == "citation_ids_valid"
                    and not validate_citation_ids(hit["result"]["answer"], len(hit["passages"]))):
                if share_publicly:
                    try:
                        cache.share_question(question)
                    except (OSError, sqlite3.Error) as error:
                        cache_failure(error)
                return {**hit, "cache_hit": True}
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            cache_failure(error)
            token = None

    query = rewrite_query(question, history)
    passages = hybrid_search_and_rerank(query)
    result = generate_grounded_answer(question=query, passages=passages)
    payload = {"query": query, "passages": passages, "result": result}
    if eligible and token is not None and result["status"] == "citation_ids_valid" and not result["citation_errors"]:
        try:
            if official_passages(passages):
                cache.put(question, token, payload)
                if share_publicly:
                    cache.share_question(question)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            cache_failure(error)
    return {**payload, "cache_hit": False}
