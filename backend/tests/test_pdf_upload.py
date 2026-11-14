from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from starlette.datastructures import UploadFile

from app.main import app
from app.pdf_upload import PdfUploadError, extract_pdf_pages


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def make_text_pdf(page_texts):
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    page_ids = [3 + 2 * index for index in range(len(page_texts))]
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()
    )
    for index, text in enumerate(page_texts):
        page_id = page_ids[index]
        content_id = page_id + 1
        escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 12 Tf 72 72 Td ({escaped_text}) Tj ET".encode()
        objects.extend(
            [
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
                    f"/Resources << /Font << /F1 {len(page_texts) * 2 + 3} 0 R >> >> "
                    f"/Contents {content_id} 0 R >>"
                ).encode(),
                f"<< /Length {len(stream)} >>\nstream\n".encode()
                + stream
                + b"\nendstream",
            ]
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(pdf)


def make_blank_pdf(*, encrypted=False):
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=144)
    if encrypted:
        writer.encrypt("password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_extract_pdf_pages_returns_one_based_page_numbers():
    pages = extract_pdf_pages(make_text_pdf(["First page", "Second page"]))

    assert [page_number for page_number, _ in pages] == [1, 2]
    assert "First page" in pages[0][1]
    assert "Second page" in pages[1][1]


def test_valid_text_pdf_returns_temporary_not_implemented_response(client):
    response = client.post(
        "/api/upload/plan",
        files={"file": ("plan.pdf", make_text_pdf(["Synthetic plan text"]), "application/pdf")},
    )

    assert response.status_code == 501
    assert response.json()["detail"] == "Plan extraction is not connected yet."


@pytest.mark.parametrize(
    ("pdf_bytes", "expected_message"),
    [
        (b"", "Uploaded PDF is empty."),
        (b"not a PDF", "Uploaded file is not a readable PDF."),
        (make_blank_pdf(), "PDF contains no extractable text."),
        (make_blank_pdf(encrypted=True), "Encrypted PDFs are not supported."),
    ],
    ids=["empty", "malformed", "textless", "encrypted"],
)
def test_rejected_pdf_inputs_return_clear_400(client, pdf_bytes, expected_message):
    response = client.post(
        "/api/upload/plan",
        files={"file": ("plan.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == expected_message
    assert "Traceback" not in response.text


def test_oversized_pdf_is_rejected(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    response = client.post(
        "/api/upload/plan",
        files={"file": ("large.pdf", b"x" * (1024 * 1024 + 1), "application/pdf")},
    )

    assert response.status_code == 413
    assert "1 MB" in response.json()["detail"]


def test_upload_reads_limit_plus_one_and_always_closes(client, monkeypatch):
    requested_sizes = []
    close_count = 0
    original_read = UploadFile.read
    original_close = UploadFile.close

    async def tracked_read(upload, size=-1):
        requested_sizes.append(size)
        return await original_read(upload, size)

    async def tracked_close(upload):
        nonlocal close_count
        close_count += 1
        await original_close(upload)

    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    monkeypatch.setattr(UploadFile, "read", tracked_read)
    monkeypatch.setattr(UploadFile, "close", tracked_close)
    response = client.post(
        "/api/upload/plan",
        files={"file": ("plan.pdf", make_text_pdf(["Synthetic plan text"]), "application/pdf")},
    )

    assert response.status_code == 501
    assert requested_sizes == [1024 * 1024 + 1]
    assert close_count >= 1
