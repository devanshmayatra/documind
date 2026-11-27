"""Shared exact-question cache; no network calls or model initialization."""
from contextlib import contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import time
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data/cache/answers.sqlite3"


def normalize_question(question):
    # Preserve punctuation, negation, numbers and location distinctions.
    return " ".join(unicodedata.normalize("NFC", question).lower().split())


def is_general_question(question, history):
    """Conservative heuristic, not a guarantee of detecting personal information."""
    text = normalize_question(question)
    return (
        not history and 10 <= len(text) <= 500
        and bool(re.match(r"^(what|when|where|how|does|do|is|are|can|must)\b", text))
        and not re.search(r"\b(i|i'm|i’ve|i've|me|my|mine|we|our|us|you|your)\b", text)
        and not re.search(r"@|https?://|\b\d{5,}\b|\b(name|passport|sevis id|student id|email|phone)\b", text)
    )


def source_manifest():
    """Only locally registered official snapshots can seed shared answers."""
    registry = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    manifest = {}
    for source_id, registered in registry.items():
        snapshots = sorted((ROOT / "data/sources" / source_id).glob("*/metadata.json"))
        if not snapshots:
            continue
        metadata = json.loads(snapshots[-1].read_text(encoding="utf-8"))
        if metadata.get("source_url") == registered["source_url"]:
            manifest[source_id] = metadata
    return manifest


def pipeline_fingerprint():
    digest = hashlib.sha256()
    for name in ("sources.json", "core/generator.py", "core/retriever.py",
                 "core/qdrant_engine.py", "core/answer_cache.py", "core/answer_service.py"):
        digest.update((ROOT / name).read_bytes())
    digest.update(os.getenv("QDRANT_URL", "http://localhost:6333").encode())
    digest.update(json.dumps(source_manifest(), sort_keys=True).encode())
    return digest.hexdigest()


def official_passages(passages):
    manifest = source_manifest()
    return bool(passages) and all(
        passage.get("source_id") in manifest
        and passage.get("source_url") == manifest[passage["source_id"]]["source_url"]
        and passage.get("source_content_sha256") == manifest[passage["source_id"]].get("content_sha256")
        and bool(passage.get("source_content_sha256"))
        and passage.get("retrieved_at") == manifest[passage["source_id"]].get("retrieved_at")
        for passage in passages
    )


class AnswerCache:
    def __init__(self, path=DEFAULT_PATH, ttl_seconds=86400):
        self.path = Path(path)
        self.ttl = ttl_seconds

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute("CREATE TABLE IF NOT EXISTS corpus (id INTEGER PRIMARY KEY, revision INTEGER, updating INTEGER)")
            db.execute("INSERT OR IGNORE INTO corpus VALUES (1, 0, 0)")
            db.execute("CREATE TABLE IF NOT EXISTS answers (key TEXT PRIMARY KEY, revision INTEGER, expires REAL, payload TEXT)")
            db.execute("""CREATE TABLE IF NOT EXISTS public_questions (
                normalized TEXT PRIMARY KEY, question TEXT NOT NULL, shared_at REAL NOT NULL
            )""")
            db.commit()
            with db:
                yield db
        finally:
            db.close()

    def token(self):
        with self.connect() as db:
            revision, updating = db.execute("SELECT revision, updating FROM corpus WHERE id=1").fetchone()
        return None if updating else (pipeline_fingerprint(), revision)

    def key(self, question, token):
        return hashlib.sha256(json.dumps([normalize_question(question), token]).encode()).hexdigest()

    def share_question(self, question):
        if not is_general_question(question, []):
            return
        with self.connect() as db:
            db.execute("""INSERT INTO public_questions VALUES (?, ?, ?)
                          ON CONFLICT(normalized) DO UPDATE SET shared_at=excluded.shared_at""",
                       (normalize_question(question), " ".join(question.split()), time.time()))

    def recent_questions(self):
        with self.connect() as db:
            rows = db.execute("""SELECT question FROM public_questions
                                 ORDER BY shared_at DESC, normalized LIMIT 50""").fetchall()
        return [question for (question,) in rows]

    def get(self, question, token):
        if token is None or token != self.token():
            return None
        with self.connect() as db:
            db.execute("DELETE FROM answers WHERE expires <= ?", (time.time(),))
            row = db.execute("SELECT payload FROM answers WHERE key=? AND expires>?",
                             (self.key(question, token), time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, question, token, payload):
        if token is None or token != self.token():
            return
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            revision, updating = db.execute("SELECT revision, updating FROM corpus WHERE id=1").fetchone()
            if updating or revision != token[1]:
                return
            db.execute("DELETE FROM answers WHERE expires <= ?", (time.time(),))
            db.execute("INSERT OR REPLACE INTO answers VALUES (?, ?, ?, ?)", (
                self.key(question, token), revision, time.time() + self.ttl,
                json.dumps(payload, default=str),
            ))

    @contextmanager
    def corpus_update(self):
        # Invalidation brackets ingestion, including failed or partial uploads.
        # A process crash leaves updating>0, disabling cache until operator repair.
        with self.connect() as db:
            db.execute("UPDATE corpus SET revision=revision+1, updating=updating+1 WHERE id=1")
            db.execute("DELETE FROM answers")
        try:
            yield
        finally:
            with self.connect() as db:
                db.execute("UPDATE corpus SET revision=revision+1, updating=updating-1 WHERE id=1")


def cache_failure(error):
    logging.getLogger(__name__).warning("Answer cache unavailable (%s)", type(error).__name__)
