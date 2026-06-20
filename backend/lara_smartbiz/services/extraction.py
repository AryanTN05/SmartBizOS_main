"""Document extraction. Returns text + per-format metadata so the upload
pipeline can persist size/mime/page-count and tell the UI whether parsing
succeeded.

Supported types (best-effort, advertised in the Documents page copy as
"PDF, DOCX, TXT, MD"):
  - application/pdf  → PyMuPDF, full text + page_count
  - text/* (txt, md) → utf-8 decode
  - application/json → utf-8 decode (the bytes ARE the text)

DOCX is NOT currently extracted — falls into the utf-8 path and likely
returns garbled bytes. Treated as 'failed' so the UI shows an error chip
instead of silently ingesting noise.
"""

from typing import Any
import fitz  # PyMuPDF


def _is_pdf(content_type: str, filename: str) -> bool:
    ct = (content_type or "").lower()
    return "pdf" in ct or filename.lower().endswith(".pdf")


def _is_text(content_type: str, filename: str) -> bool:
    ct = (content_type or "").lower()
    if ct.startswith("text/") or "json" in ct:
        return True
    return any(filename.lower().endswith(ext) for ext in (".txt", ".md", ".markdown", ".log"))


async def extract(contents: bytes, content_type: str, filename: str = "") -> dict[str, Any]:
    """Extract text + metadata.

    Returns: {
        "text": str,                    # extracted (possibly empty)
        "page_count": int | None,       # PDFs only
        "mime_type": str,               # normalised
        "size_bytes": int,
        "status": "ready" | "failed",
        "error": str | None,
    }
    """
    size = len(contents or b"")
    mime = (content_type or "").lower()

    if _is_pdf(content_type, filename):
        try:
            doc = fitz.open(stream=contents, filetype="pdf")
            pages = doc.page_count
            text = "".join(page.get_text() + "\n" for page in doc).strip()
            return {
                "text": text, "page_count": pages, "mime_type": mime or "application/pdf",
                "size_bytes": size, "status": "ready", "error": None,
            }
        except Exception as e:
            return {
                "text": "", "page_count": None, "mime_type": mime or "application/pdf",
                "size_bytes": size, "status": "failed", "error": f"PDF parse failed: {e}",
            }

    if _is_text(content_type, filename):
        try:
            text = contents.decode("utf-8").strip()
            return {
                "text": text, "page_count": None, "mime_type": mime or "text/plain",
                "size_bytes": size, "status": "ready", "error": None,
            }
        except Exception as e:
            return {
                "text": "", "page_count": None, "mime_type": mime or "text/plain",
                "size_bytes": size, "status": "failed", "error": f"Text decode failed: {e}",
            }

    return {
        "text": "", "page_count": None, "mime_type": mime or "application/octet-stream",
        "size_bytes": size, "status": "failed",
        "error": f"Unsupported file type: {mime or '(unknown)'}. PDF and plain text only.",
    }
