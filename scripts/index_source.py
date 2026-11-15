import argparse
import hashlib
import json
import uuid
from pathlib import Path

from core.ingestion import extract_chunks_with_metadata
from core.qdrant_engine import upload_chunks


ROOT = Path(__file__).resolve().parents[1]
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100


def index_source(source_id):
    source_folder = ROOT / "data" / "sources" / source_id
    snapshot = max(p for p in source_folder.iterdir() if p.is_dir())

    metadata = json.loads(
        (snapshot / "metadata.json").read_text(encoding="utf-8")
    )

    if metadata["source_id"] != source_id:
        raise ValueError("Snapshot source ID does not match the requested source.")

    content_path = snapshot / "content.txt"
    text_hash = hashlib.sha256(content_path.read_bytes()).hexdigest()

    chunks = extract_chunks_with_metadata(
        str(content_path),
        chunk_size=CHUNK_SIZE,
        overlap=CHUNK_OVERLAP,
        original_filename=f"{source_id}.txt",
        source_url=metadata["source_url"],
        publisher=metadata["publisher"],
    )

    if not chunks:
        raise ValueError("No readable chunks were produced.")

    for index, chunk in enumerate(chunks):
        identity = json.dumps([
            "f1-compass",
            metadata["source_url"],
            text_hash,
            CHUNK_SIZE,
            CHUNK_OVERLAP,
            index,
        ])

        chunk.update({
            "chunk_id": str(uuid.uuid5(uuid.NAMESPACE_URL, identity)),
            "chunk_index": index,
            "source_id": source_id,
            "source_title": metadata["title"],
            "university": metadata["university"],
            "topic": metadata["topic"],
            "source_type": metadata["source_type"],
            "retrieved_at": metadata["retrieved_at"],
            "source_updated_at": metadata.get("source_updated_at"),
            "source_content_sha256": metadata["content_sha256"],
            "extracted_content_sha256": text_hash,
        })

    print(f"Source: {metadata['title']}")
    print(f"Snapshot: {snapshot.name}")
    print(f"Uploading {len(chunks)} chunks...", flush=True)

    upload_chunks(chunks)

    print("Source indexing completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_id")
    args = parser.parse_args()

    index_source(args.source_id)