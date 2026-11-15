import argparse
import json
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]


def table_to_text(table, table_number):
    """Convert table rows into explicitly labelled records."""
    if table.select("[rowspan], [colspan]"):
        raise ValueError("Merged table cells need a dedicated extraction rule.")

    rows = table.find_all("tr")
    if not rows:
        raise ValueError("Encountered an empty table.")

    headers = [
        cell.get_text(" ", strip=True)
        for cell in rows[0].find_all(["th", "td"])
    ]

    records = []

    for row_number, row in enumerate(rows[1:], start=1):
        values = [
            cell.get_text(" ", strip=True)
            for cell in row.find_all(["th", "td"])
        ]

        if len(values) != len(headers):
            raise ValueError(
                f"Table {table_number}, row {row_number}: "
                "column count does not match the header."
            )

        fields = [
            f"{header or 'Row label'}: {value or '[blank in source]'}"
            for header, value in zip(headers, values)
        ]

        records.append(
            f"Table {table_number}, row {row_number}\n"
            + "\n".join(fields)
        )

    return "\n\n".join(records)


def extract_source(source_id):
    source_folder = ROOT / "data" / "sources" / source_id
    snapshot = max(p for p in source_folder.iterdir() if p.is_dir())

    metadata = json.loads(
        (snapshot / "metadata.json").read_text(encoding="utf-8")
    )

    soup = BeautifulSoup(
        (snapshot / "page.html").read_bytes(),
        "html.parser",
        from_encoding=metadata["encoding"],
    )

    main = soup.find("main")
    if main is None:
        raise ValueError("Main content area not found.")

    titles = [h.get_text(" ", strip=True) for h in main.find_all("h1")]
    if metadata["title"] not in titles:
        raise ValueError("Expected article title not found inside main content.")

    for element in main.select("script, style, nav, footer, form"):
        element.decompose()

    tables = main.find_all("table")
    for number, table in enumerate(tables, start=1):
        table.replace_with("\n\n" + table_to_text(table, number) + "\n\n")

    for inline in main.find_all(
        ["a", "strong", "b", "em", "i", "span", "u", "small", "sup", "sub"]
    ):
        inline.unwrap()

    # Merge adjacent text nodes before extracting text.
    main.smooth()

    text = main.get_text("\n", strip=True)

    if not text.strip():
        raise ValueError("Extraction produced empty text.")

    output_path = snapshot / "content.txt"
    output_path.write_text(text, encoding="utf-8")

    print(f"Saved: {output_path}")
    print(f"Characters: {len(text):,}")
    print(f"Tables converted: {len(tables)}")
    print("\nPreview:\n")
    print(text[:1500])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_id")
    args = parser.parse_args()

    extract_source(args.source_id)