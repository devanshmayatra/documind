import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def fetch_source(source_id: str):
    registry = json.loads(
        (ROOT / "sources.json").read_text(encoding="utf-8")
    )
    source = registry[source_id]
    url = source["source_url"]

    request = Request(
        url,
        headers={
            "User-Agent": "F1Compass/0.1",
            "Accept": "text/html",
        },
    )

    with urlopen(request, timeout=30) as response:
        final_url = response.geturl()

        # Stop if the request redirects to a different website.
        if urlsplit(final_url).hostname != urlsplit(url).hostname:
            raise ValueError(f"Unexpected redirect: {final_url}")

        if response.headers.get_content_type() != "text/html":
            raise ValueError("Expected an HTML webpage.")

        raw_html = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"

    if not raw_html.strip():
        raise ValueError("The downloaded page is empty.")

    retrieved_at = datetime.now(timezone.utc)
    snapshot_name = retrieved_at.strftime("%Y%m%dT%H%M%S%fZ")
    folder = ROOT / "data" / "sources" / source_id / snapshot_name
    folder.mkdir(parents=True, exist_ok=False)

    # Preserve the original response bytes.
    (folder / "page.html").write_bytes(raw_html)

    metadata = {
        **source,
        "source_id": source_id,
        "retrieved_at": retrieved_at.isoformat(),
        "final_url": final_url,
        "encoding": encoding,
        "content_sha256": hashlib.sha256(raw_html).hexdigest(),
    }

    (folder / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Saved source: {source['title']}")
    print(f"Snapshot folder: {folder}")
    print(f"Downloaded bytes: {len(raw_html):,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_id", help="Source ID from sources.json")
    args = parser.parse_args()

    fetch_source(args.source_id)