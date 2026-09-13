import os
from pypdf import PdfReader
from docx import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

def read_text_file(file_path: str) -> str:
    """Safely reads text files across Windows and Linux encodings."""
    encodings = ["utf-8", "utf-8-sig", "utf-16", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc) as f:
                content = f.read()
                if content.strip():
                    return content
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""

def extract_chunks_with_metadata(file_path: str, chunk_size: int = 1000, overlap: int = 100):
    ext = os.path.splitext(file_path)[1].lower()
    filename = os.path.basename(file_path)
    # Strip temporary prefix if created via NamedTemporaryFile
    clean_filename = filename.split("_", 1)[-1] if "_" in filename else filename
    extracted_chunks = []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", " ", ""]
    )

    if ext == ".pdf":
        reader = PdfReader(file_path)
        for page_idx, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if text:
                for chunk in splitter.split_text(text):
                    if chunk.strip():
                        extracted_chunks.append({
                            "text": chunk.strip(),
                            "source": clean_filename,
                            "page": page_idx + 1
                        })

    elif ext in [".docx", ".doc"]:
        doc = Document(file_path)
        text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        if text.strip():
            for chunk in splitter.split_text(text):
                if chunk.strip():
                    extracted_chunks.append({
                        "text": chunk.strip(),
                        "source": clean_filename,
                        "page": 1
                    })

    elif ext in [".txt", ".md", ".csv"]:
        text = read_text_file(file_path)
        if text.strip():
            for chunk in splitter.split_text(text):
                if chunk.strip():
                    extracted_chunks.append({
                        "text": chunk.strip(),
                        "source": clean_filename,
                        "page": 1
                    })

    return extracted_chunks