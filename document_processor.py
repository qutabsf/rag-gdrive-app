"""Document text extraction and chunking."""

import io


def extract_text(raw_bytes: bytes, mime_type: str, file_name: str = "") -> str:
    """Extract plain text from raw bytes given the MIME type."""
    if mime_type == "application/pdf":
        return _extract_pdf(raw_bytes)
    if mime_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ):
        return _extract_docx(raw_bytes)
    # Plain text, CSV, or already-exported Google Workspace content
    try:
        return raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    except Exception as exc:
        return f"[PDF extraction error: {exc}]"


def _extract_docx(data: bytes) -> str:
    try:
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as exc:
        return f"[DOCX extraction error: {exc}]"


def chunk_text(
    text: str,
    metadata: dict,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[dict]:
    """Split text into overlapping chunks and attach metadata.

    Returns a list of dicts with keys 'text' and 'metadata'.
    """
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()

        # Try to end on a sentence or paragraph boundary
        if end < len(text):
            for boundary in ("\n\n", "\n", ". ", "? ", "! "):
                idx = chunk.rfind(boundary)
                if idx > chunk_size // 2:
                    chunk = chunk[: idx + len(boundary)].strip()
                    end = start + idx + len(boundary)
                    break

        if chunk:
            chunks.append(
                {
                    "text": chunk,
                    "metadata": {**metadata, "chunk_index": chunk_index},
                }
            )
            chunk_index += 1

        start = end - chunk_overlap
        if start >= len(text) - chunk_overlap:
            break

    return chunks
