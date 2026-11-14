"""In-memory PDF validation and page-indexed text extraction."""
from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader


class PdfUploadError(ValueError):
    """A PDF could not be safely read or did not contain usable text."""


def extract_pdf_pages(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Return each page's extracted text with its 1-based page number."""
    if not pdf_bytes:
        raise PdfUploadError("Uploaded PDF is empty.")

    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
    except Exception as exc:
        raise PdfUploadError("Uploaded file is not a readable PDF.") from exc

    try:
        if reader.is_encrypted:
            raise PdfUploadError("Encrypted PDFs are not supported.")

        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                raise PdfUploadError(
                    f"Could not extract text from PDF page {page_number}."
                ) from exc
            pages.append((page_number, text))
    except PdfUploadError:
        raise
    except Exception as exc:
        raise PdfUploadError("Uploaded file is not a readable PDF.") from exc

    if not any(text.strip() for _, text in pages):
        raise PdfUploadError("PDF contains no extractable text.")
    return pages